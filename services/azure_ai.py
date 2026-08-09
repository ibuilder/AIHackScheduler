import json
import os
from datetime import datetime, timezone
from typing import Any

from extensions import db  # noqa: F401  -- imported for session access by callers
from models import Project, Task, TaskStatus
from services.optional import IntegrationUnavailable, require, require_settings


class AzureAIService:
    """Wrapper around an Azure OpenAI deployment.

    The client is built lazily so that importing this module — which the Azure
    blueprint does at import time — never requires the ``openai`` package or a
    configured endpoint.
    """

    FEATURE = "Azure AI"

    def __init__(self):
        self.api_key = os.getenv("FOUNDRY_API_KEY")
        self.endpoint = os.getenv("FOUNDRY_ENDPOINT")
        self.model_name = os.getenv("FOUNDRY_MODEL_NAME", "gpt-4o")
        self._client = None

    @property
    def available(self) -> bool:
        """Whether a call could succeed, without attempting one."""
        try:
            self._ensure_client()
        except IntegrationUnavailable:
            return False
        return True

    def _ensure_client(self):
        if self._client is None:
            require_settings(
                self.FEATURE,
                FOUNDRY_API_KEY=self.api_key,
                FOUNDRY_ENDPOINT=self.endpoint,
            )
            openai = require("openai", feature=self.FEATURE)
            self._client = openai.AzureOpenAI(
                api_key=self.api_key,
                api_version="2024-02-01",
                azure_endpoint=self.endpoint,
            )
        return self._client

    def _complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        """Call the model and parse a JSON reply.

        ``response_format`` is requested so the model returns parseable JSON.
        The previous code called ``json.loads`` on free-form prose, so a
        perfectly good answer surfaced to users as a decode error.
        """
        client = self._ensure_client()
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned unparseable JSON: {exc}") from exc

    # ------------------------------------------------------------------
    # Every method below grounds the model in deterministic CPM output.
    # Handing an LLM a bare list of task rows and asking for "critical path
    # analysis" invites it to invent one. The engine in core.cpm computes the
    # real path, float and duration; the model's job is interpretation and
    # narrative, not arithmetic.
    # ------------------------------------------------------------------

    def _grounding(self, project_id: int) -> dict[str, Any]:
        from services.schedule_analysis import analyse_project, health_check

        return {
            "cpm": analyse_project(project_id),
            "schedule_quality": health_check(project_id),
        }

    def analyze_project_schedule(self, project_id: int) -> dict[str, Any]:
        """Interpret a computed schedule: risks, bottlenecks, recommendations."""
        project = db.session.get(Project, project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        tasks = Task.query.filter_by(project_id=project_id).all()
        grounding = self._grounding(project_id)

        project_data = {
            "project_name": project.name,
            "start_date": project.start_date.isoformat(),
            "end_date": project.end_date.isoformat(),
            "total_tasks": len(tasks),
            "computed_critical_path": grounding["cpm"].get("critical_path"),
            "computed_duration_days": grounding["cpm"].get("project_duration_days"),
            "schedule_quality_grade": grounding["schedule_quality"].get("grade"),
            "failed_quality_checks": [
                c["name"]
                for c in grounding["schedule_quality"].get("checks", [])
                if c["status"] == "fail"
            ],
            "tasks": [
                {
                    "name": task.name,
                    "start_date": task.start_date.isoformat(),
                    "end_date": task.end_date.isoformat(),
                    "duration": task.duration,
                    "progress": task.progress,
                    "status": task.status.name,
                }
                for task in tasks
            ],
        }

        prompt = f"""Analyse this construction project. The critical path, duration
and schedule-quality grade below were computed by a deterministic CPM engine.
Treat them as given and do not recalculate them.

{json.dumps(project_data, indent=2)}

Return JSON with these keys:
  risks              list of {{severity, description, affected_activities, mitigation}}
  bottlenecks        list of {{resource_or_activity, why, suggested_action}}
  recommendations    list of {{action, expected_benefit, effort}}
  completion_outlook object with {{assessment, key_assumptions}}

Where the schedule quality grade is poor, say plainly which conclusions become
unreliable as a result."""

        try:
            analysis = self._complete(
                "You are a construction scheduling expert. You interpret computed "
                "schedule data; you never invent dates, float or critical paths.",
                prompt,
                max_tokens=2000,
                temperature=0.3,
            )
        except IntegrationUnavailable as exc:
            return exc.as_response()
        except Exception as exc:
            return {"success": False, "error": f"Azure AI analysis failed: {exc}"}

        return {
            "success": True,
            "analysis": analysis,
            "grounding": grounding,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def optimize_schedule(self, project_id: int, parameters: dict[str, Any]) -> dict[str, Any]:
        """Propose sequence and duration changes against a computed baseline."""
        project = db.session.get(Project, project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        grounding = self._grounding(project_id)
        quality = grounding["schedule_quality"]

        # Optimising an unsound network yields plausible, useless advice.
        if quality.get("success") and not quality.get("optimisable", True):
            return {
                "success": False,
                "error": "Schedule quality is too low to optimise against",
                "failed_checks": [
                    c["name"] for c in quality.get("checks", []) if c["status"] == "fail"
                ],
            }

        tasks = Task.query.filter_by(project_id=project_id).all()
        optimization_type = parameters.get("type", "time")

        project_data = {
            "project_name": project.name,
            "optimization_type": optimization_type,
            "constraints": parameters.get("constraints", {}),
            "computed_critical_path": grounding["cpm"].get("critical_path"),
            "computed_duration_days": grounding["cpm"].get("project_duration_days"),
            "activities": grounding["cpm"].get("activities", []),
            "tasks": [
                {
                    "id": task.id,
                    "name": task.name,
                    "duration": task.duration,
                    "progress": task.progress,
                    "status": task.status.name,
                    "dependencies": [dep.predecessor_task_id for dep in task.dependencies],
                }
                for task in tasks
            ],
        }

        prompt = f"""Optimise this construction schedule for {optimization_type}.
Float and the critical path below are computed. Only activities with zero total
float can shorten the project, so justify every recommendation against that.

{json.dumps(project_data, indent=2, default=str)}

Return JSON with these keys:
  sequence_changes   list of {{activity_id, change, rationale, days_saved}}
  duration_changes   list of {{activity_id, from_days, to_days, how, added_cost}}
  resource_moves     list of {{from_activity, to_activity, resource, rationale}}
  expected_savings   object with {{days, cost, confidence}}
  risks_introduced   list of {{risk, likelihood, mitigation}}"""

        try:
            optimization = self._complete(
                "You are a construction optimisation expert. Recommendations must "
                "be traceable to computed float; never claim a saving on an "
                "activity that is not on the critical path.",
                prompt,
                max_tokens=2500,
                temperature=0.2,
            )
        except IntegrationUnavailable as exc:
            return exc.as_response()
        except Exception as exc:
            return {"success": False, "error": f"Schedule optimization failed: {exc}"}

        return {
            "success": True,
            "optimization": optimization,
            "parameters": parameters,
            "grounding": grounding,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def predict_completion_date(self, project_id: int) -> dict[str, Any]:
        """Forecast completion from measured progress against the CPM baseline."""
        project = db.session.get(Project, project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        tasks = Task.query.filter_by(project_id=project_id).all()
        if not tasks:
            return {"success": False, "error": "Project has no tasks to forecast"}

        grounding = self._grounding(project_id)
        completed_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        total_progress = sum(task.progress or 0 for task in tasks) / len(tasks)

        project_metrics = {
            "total_tasks": len(tasks),
            "completed_tasks": completed_tasks,
            "remaining_tasks": len(tasks) - completed_tasks,
            "overall_progress_pct": round(total_progress, 1),
            "planned_end_date": project.end_date.isoformat(),
            "cpm_calculated_finish": grounding["cpm"].get("calculated_finish"),
            "cpm_duration_days": grounding["cpm"].get("project_duration_days"),
            "days_elapsed": (datetime.now().date() - project.start_date).days,
            "total_planned_days": (project.end_date - project.start_date).days,
            "schedule_quality_grade": grounding["schedule_quality"].get("grade"),
        }

        prompt = f"""Forecast the completion date for this construction project.
The CPM finish date below is computed from the current logic network; your job
is to say whether measured progress supports it.

{json.dumps(project_metrics, indent=2)}

Return JSON with these keys:
  forecast_date      ISO date string
  confidence         one of high, medium, low
  range              object with {{optimistic, pessimistic}} as ISO date strings
  drivers            list of {{factor, effect_days, reasoning}}
  caveats            list of strings"""

        try:
            prediction = self._complete(
                "You are a construction forecasting expert. State your confidence "
                "honestly and lower it when schedule quality is poor.",
                prompt,
                max_tokens=1000,
                temperature=0.1,
            )
        except IntegrationUnavailable as exc:
            return exc.as_response()
        except Exception as exc:
            return {"success": False, "error": f"Completion prediction failed: {exc}"}

        return {
            "success": True,
            "prediction": prediction,
            "current_metrics": project_metrics,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
