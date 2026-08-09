"""Company insight and resource optimisation.

``optimize_resource_allocation`` and ``generate_project_insights`` each called
a chain of private helpers, nine of which were never written. Both raised
``AttributeError`` on their first line of real work and the blueprint turned
that into a generic 500, so the endpoints read as unlucky rather than
impossible.

Two more helpers did exist, attached to the class at import time rather than
defined in it, and returned fixed text: "Project completion rates are stable",
"Resource utilization could be optimized", "Budget adherence is within
acceptable range" — for every company, on every request, whatever the data
said. Those sentences are the reason these tests assert on numbers.
"""

from datetime import date, timedelta

import pytest

from extensions import db
from models import Resource, ResourceAssignment, Task


@pytest.fixture
def analytics():
    from azure_ai.predictive_analytics import AzureAIPredictiveAnalytics

    return AzureAIPredictiveAnalytics()


@pytest.fixture
def bare_project(seeded):
    """A second project with one activity and no resources.

    The seeded demo project ships seven resources of its own -- including one
    called "Steel erectors" -- so asserting on totals against it measures the
    fixture as much as the code. These tests need arithmetic they control.
    """
    from models import Project

    project = Project(
        name="Resource levelling fixture",
        company_id=seeded.company_id,
        created_by=seeded.created_by,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        status="active",
    )
    db.session.add(project)
    db.session.flush()

    task = Task(
        name="Only activity",
        project_id=project.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=5),
        duration=5,
    )
    db.session.add(task)
    db.session.commit()
    return project, task


def _add_resource(project_id, name, capacity, unit_cost=None, resource_type="labor"):
    resource = Resource(
        name=name,
        type=resource_type,
        project_id=project_id,
        unit="crew-days",
        total_quantity=capacity,
        available_quantity=capacity,
        unit_cost=unit_cost,
    )
    db.session.add(resource)
    db.session.flush()
    return resource


def _assign(resource, task_id, quantity):
    db.session.add(ResourceAssignment(task_id=task_id, resource_id=resource.id, quantity=quantity))
    db.session.flush()


# ── resource optimisation ────────────────────────────────────────────────


def test_over_allocation_is_detected_and_quantified(analytics, bare_project):
    """The headline claim: committing more than capacity is arithmetic, and
    the answer must be the excess, not an adjective."""
    project, task = bare_project

    crew = _add_resource(project.id, "Steel erectors", capacity=10.0, unit_cost=850.0)
    _assign(crew, task.id, 14.0)  # 140% committed
    db.session.commit()

    current = analytics._analyze_current_resources({"project_id": project.id})

    entry = next(r for r in current["resources"] if r["name"] == "Steel erectors")
    assert entry["utilisation_percent"] == 140.0
    assert entry["over_allocated"] is True
    assert current["over_allocated"] == ["Steel erectors"]


def test_a_resource_with_no_recorded_capacity_is_not_called_overloaded(analytics, bare_project):
    """Capacity of zero means "not tracked". Dividing by it, or treating it as
    infinite overload, would put a red flag on every untracked resource."""
    project, task = bare_project

    untracked = _add_resource(project.id, "Site consumables", capacity=0.0)
    _assign(untracked, task.id, 5.0)
    db.session.commit()

    current = analytics._analyze_current_resources({"project_id": project.id})

    entry = next(r for r in current["resources"] if r["name"] == "Site consumables")
    assert entry["utilisation_percent"] is None
    assert entry["over_allocated"] is False
    assert "Site consumables" not in current["over_allocated"]


def test_suggestions_name_the_resource_and_the_number(analytics, bare_project):
    project, task = bare_project

    crew = _add_resource(project.id, "Formwork gang", capacity=8.0, unit_cost=600.0)
    _assign(crew, task.id, 12.0)
    spare = _add_resource(project.id, "Surveyors", capacity=10.0)
    _assign(spare, task.id, 2.0)
    db.session.commit()

    suggestions = analytics._ai_resource_optimization({"project_id": project.id})
    by_resource = {s["resource"]: s for s in suggestions}

    assert by_resource["Formwork gang"]["action"] == "level"
    assert by_resource["Formwork gang"]["excess_units"] == 4.0
    assert "4.0" in by_resource["Formwork gang"]["detail"]

    assert by_resource["Surveyors"]["action"] == "redeploy"
    assert by_resource["Surveyors"]["spare_units"] == 8.0


def test_the_same_data_gives_the_same_answer(analytics, bare_project):
    """Deterministic by design. A schedule review that returns different
    recommendations on a second run cannot be used to make a decision."""
    project, task = bare_project
    crew = _add_resource(project.id, "Crane crew", capacity=5.0)
    _assign(crew, task.id, 9.0)
    db.session.commit()

    first = analytics._ai_resource_optimization({"project_id": project.id})
    second = analytics._ai_resource_optimization({"project_id": project.id})
    assert first == second


def test_cost_impact_prices_excess_and_admits_what_it_cannot_price(analytics, bare_project):
    project, task = bare_project

    priced = _add_resource(project.id, "Electricians", capacity=6.0, unit_cost=700.0)
    _assign(priced, task.id, 9.0)  # 3 units over
    unpriced = _add_resource(project.id, "Labourers", capacity=4.0, unit_cost=None)
    _assign(unpriced, task.id, 6.0)  # 2 units over, no rate
    db.session.commit()

    suggestions = analytics._ai_resource_optimization({"project_id": project.id})
    impact = analytics._calculate_cost_impact(suggestions)

    assert impact["over_allocation_cost"] == pytest.approx(3 * 700.0)
    # Silently costing the unpriced resource at zero would understate the total.
    assert impact["resources_without_a_unit_cost"] == ["Labourers"]


def test_efficiency_gains_cap_absorbable_work_at_the_idle_capacity(analytics, bare_project):
    """Over-allocation can only be absorbed by capacity that exists."""
    project, task = bare_project

    over = _add_resource(project.id, "Fitters", capacity=5.0)
    _assign(over, task.id, 15.0)  # 10 units over
    idle = _add_resource(project.id, "Painters", capacity=10.0)
    _assign(idle, task.id, 8.0)  # only 2 spare
    db.session.commit()

    current = analytics._analyze_current_resources({"project_id": project.id})
    suggestions = analytics._ai_resource_optimization({"project_id": project.id})
    gains = analytics._calculate_efficiency_gains(current, suggestions)

    assert gains["over_allocated_units"] == 10.0
    assert gains["absorbable_units"] == 0.0  # Painters at 80% are not idle
    assert gains["utilisation_spread_percent"] > 0


def test_priorities_put_the_worst_over_allocation_first(analytics, bare_project):
    project, task = bare_project

    _assign(_add_resource(project.id, "Mild", capacity=10.0), task.id, 11.0)  # 110%
    _assign(_add_resource(project.id, "Severe", capacity=10.0), task.id, 20.0)  # 200%
    _assign(_add_resource(project.id, "Spare", capacity=10.0), task.id, 1.0)  # 10%
    db.session.commit()

    ordered = analytics._prioritize_optimizations(
        analytics._ai_resource_optimization({"project_id": project.id})
    )

    assert [s["priority"] for s in ordered] == list(range(1, len(ordered) + 1))
    assert ordered[0]["resource"] == "Severe"
    assert ordered[-1]["resource"] == "Spare"


def test_the_whole_optimisation_endpoint_returns_a_result(signed_in):
    """End to end. This returned 500 on every request before the helpers
    existed, because the first one it called did not."""
    client, project, _ = signed_in

    response = client.get(f"/api/ai/resource-optimization/{project.id}")
    assert response.status_code == 200, response.get_data(as_text=True)

    body = response.get_json()
    assert body["project_id"] == project.id
    for key in (
        "current_allocation",
        "optimization_suggestions",
        "efficiency_gains",
        "cost_impact",
        "implementation_priority",
    ):
        assert key in body, f"{key} missing from the response"


# ── company insight ──────────────────────────────────────────────────────


def test_history_is_bucketed_so_a_trend_can_exist(analytics, seeded):
    """The previous version returned four totals for the whole window, which
    is a snapshot. _analyze_trends had nothing to compare against."""
    history = analytics._gather_historical_data(seeded.company_id, 90)

    assert len(history["periods"]) == 6
    assert sum(p["started"] for p in history["periods"]) == history["projects"]


def test_insights_report_measured_numbers_not_fixed_sentences(analytics, seeded):
    history = analytics._gather_historical_data(seeded.company_id, 90)
    insights = analytics._ai_company_insights(history)

    assert insights["projects_in_window"] >= 1
    assert insights["completion_rate_percent"] is not None
    # The demo project carries real transactions, so spend is not zero.
    assert insights["recorded_spend"] > 0
    assert str(insights["projects_in_window"]) in insights["performance_summary"]

    # The sentences the old implementation always returned.
    for invented in (
        "Project completion rates are stable",
        "Resource utilization could be optimized",
        "Budget adherence is within acceptable range",
    ):
        assert invented not in str(insights)


def test_trends_refuse_to_report_one_without_enough_history(analytics):
    assert analytics._analyze_trends({"periods": []})["available"] is False
    assert (
        analytics._analyze_trends({"periods": [{"started": 1, "completed": 0}]})["available"]
        is False
    )


def test_a_forecast_is_withheld_when_nothing_has_completed(analytics, seeded):
    """Projecting a completion rate from zero completions is division by
    wishful thinking. It says so instead."""
    history = analytics._gather_historical_data(seeded.company_id, 90)
    assert history["completed"] == 0

    forecast = analytics._predict_future_performance(history)
    assert forecast["available"] is False
    assert "completed" in forecast["reason"]


def test_benchmarking_uses_dcma_rather_than_an_invented_average(analytics, seeded):
    history = analytics._gather_historical_data(seeded.company_id, 90)
    benchmark = analytics._industry_benchmarking(history)

    assert benchmark["available"] is True
    assert benchmark["standard"] == "DCMA 14-Point Schedule Assessment"
    assert 0 <= benchmark["mean_health_score"] <= 100
    assert benchmark["band"] in {"strong", "acceptable", "weak", "poor"}


def test_recommendations_cite_the_number_that_triggered_them(analytics, seeded):
    history = analytics._gather_historical_data(seeded.company_id, 90)
    insights = analytics._ai_company_insights(history)
    trends = analytics._analyze_trends(history)

    recommendations = analytics._strategic_recommendations(insights, trends)
    assert recommendations

    # The demo project has completed nothing, so the delivery threshold fires.
    themes = {r["theme"] for r in recommendations}
    assert "delivery" in themes
    text = " ".join(r["recommendation"] for r in recommendations)
    assert "%" in text


def test_recommendations_say_so_when_nothing_needs_attention(analytics):
    """A page of advice generated for a healthy portfolio is noise."""
    healthy = {
        "completion_rate_percent": 92.0,
        "projects_below_health_threshold": [],
        "projects_over_budget": [],
    }
    flat = {"available": True, "projects_completed": {"direction": "flat"}}

    recommendations = analytics._strategic_recommendations(healthy, flat)
    assert len(recommendations) == 1
    assert recommendations[0]["theme"] == "steady state"


def test_the_whole_insights_endpoint_returns_a_result(signed_in):
    client, _, _ = signed_in

    response = client.get("/api/ai/company-insights")
    assert response.status_code == 200, response.get_data(as_text=True)

    body = response.get_json()
    for key in (
        "ai_insights",
        "performance_trends",
        "future_predictions",
        "benchmarking",
        "strategic_recommendations",
    ):
        assert key in body, f"{key} missing from the response"


def test_an_over_budget_project_is_named(analytics, seeded):
    """Budget adherence used to be reported as "within acceptable range"
    unconditionally."""
    from models import Transaction, TransactionType

    project = seeded
    project.budget = 1000.0
    db.session.add(
        Transaction(
            transaction_number="TXN-OVERSPEND-1",
            project_id=project.id,
            company_id=project.company_id,
            created_by_id=project.created_by,
            amount=5000.0,
            transaction_type=TransactionType.EXPENSE,
            description="Overspend",
            transaction_date=date.today() - timedelta(days=1),
        )
    )
    db.session.commit()

    history = analytics._gather_historical_data(project.company_id, 90)
    insights = analytics._ai_company_insights(history)

    assert project.name in insights["projects_over_budget"]
