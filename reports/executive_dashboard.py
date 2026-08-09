"""
Executive Dashboard for BBSchedule Platform
High-level analytics and KPIs for executive decision making
"""

from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import Equipment, Invoice, Project, Transaction, TransactionType, User

executive_bp = Blueprint("executive", __name__)


class ExecutiveDashboard:
    """Executive-level analytics and reporting"""

    def __init__(self):
        pass

    def get_company_overview(self, company_id, date_range_days=30):
        """Get high-level company performance overview"""
        end_date = date.today()
        end_date - timedelta(days=date_range_days)

        # Basic project metrics
        total_projects = Project.query.filter_by(company_id=company_id).count()
        active_projects = Project.query.filter_by(company_id=company_id, status="active").count()
        completed_projects = Project.query.filter_by(
            company_id=company_id, status="completed"
        ).count()

        # Financial metrics (simplified - would integrate with actual financial data)
        projects = Project.query.filter_by(company_id=company_id).all()
        total_contract_value = sum(p.budget for p in projects if p.budget) or 0

        # Calculate revenue recognition (simplified)
        completed_value = (
            sum(p.budget for p in projects if p.budget and p.status == "completed") or 0
        )

        # Margin from the ledger, or nothing. This was `profit_margin = 0.12`
        # and `budget_variance = 0.05` — two constants presented to an executive
        # as measurements. Both are computed now, and both are None until there
        # are transactions to compute them from.
        ledger = self._ledger_totals(company_id)
        profit_margin = ledger["margin_percent"]
        estimated_profit = ledger["profit"]
        budget_variance = self._budget_variance(company_id, projects)

        # Resource utilization
        total_users = User.query.filter_by(company_id=company_id, is_active=True).count()

        overdue_projects = 0

        for project in projects:
            if project.end_date and project.end_date < end_date and project.status != "completed":
                overdue_projects += 1

        return {
            "projects": {
                "total": total_projects,
                "active": active_projects,
                "completed": completed_projects,
                "overdue": overdue_projects,
                "completion_rate": (completed_projects / total_projects * 100)
                if total_projects > 0
                else 0,
            },
            "financial": {
                "total_contract_value": total_contract_value,
                "completed_value": completed_value,
                # None where the ledger holds nothing to measure. A caller
                # should render "no data yet", not a zero that reads as a fact.
                "recorded_income": ledger["income"],
                "recorded_expense": ledger["expense"],
                "estimated_profit": estimated_profit,
                "profit_margin": profit_margin,
                "budget_variance": budget_variance,
                "measured": ledger["measured"],
                "note": (
                    None
                    if ledger["measured"]
                    else "No income or expense transactions recorded, so margin cannot be "
                    "measured. Record transactions against projects and these populate "
                    "with no further change."
                ),
            },
            "resources": {
                "total_staff": total_users,
                # Measured from logged equipment hours over the last 30 days.
                # Previously a hardcoded 78.5 alongside a "productivity index"
                # that was not derived from anything at all, so it has gone.
                "equipment_utilization_rate": self._fleet_utilization(company_id),
            },
            "risk_indicators": {
                "overdue_projects": overdue_projects,
                # Graded from the same overdue count the caller can see, rather
                # than asserted as a constant "Medium" for every company.
                "schedule_risk_score": self._grade_overdue(overdue_projects, total_projects),
                "overall_health": self._grade_overdue(overdue_projects, total_projects),
            },
        }

    # Construction templates carry the sector in their id, so a project created
    # from one already records what it is. Projects created directly do not.
    TEMPLATE_SECTORS = {
        "commercial_office": "Commercial",
        "retail_center": "Commercial",
        "residential_complex": "Residential",
        "industrial_warehouse": "Industrial",
        "infrastructure_road": "Infrastructure",
        "hospital_medical": "Healthcare",
    }

    @classmethod
    def _by_sector(cls, projects: list, spend: dict[int, float]) -> list[dict]:
        """Portfolio by sector, inferred from the template a project came from.

        This was four hardcoded rows — Commercial 15 projects, $18.5M, 11.2%
        margin — identical for every company and unmoved by anything anyone did.

        There is no sector column, so the sector is read from ``template_used``,
        which a project created from a construction template already records.
        Anything else is reported as Unspecified rather than guessed at.

        **Extension path:** add a ``sector`` column to ``Project``, prefer it
        here and fall back to the template mapping. Nothing else in this method
        changes, and the payload shape stays the same for the UI.
        """
        grouped: dict[str, dict] = {}
        for project in projects:
            sector = cls.TEMPLATE_SECTORS.get(project.template_used or "", "Unspecified")
            entry = grouped.setdefault(
                sector,
                {"sector": sector, "projects": 0, "contract_value": 0.0, "recorded_spend": 0.0},
            )
            entry["projects"] += 1
            entry["contract_value"] += float(project.budget or 0)
            entry["recorded_spend"] += spend.get(project.id, 0.0)

        for entry in grouped.values():
            value = entry["contract_value"]
            cost = entry["recorded_spend"]
            entry["contract_value"] = round(value, 2)
            entry["recorded_spend"] = round(cost, 2)
            # Deliberately budget consumed, not margin. Margin on unfinished
            # work is money not yet spent, and calling it margin makes an
            # untouched project look like the most profitable in the book.
            entry["budget_consumed_percent"] = (
                round(cost / value * 100, 1) if value and cost else None
            )

        return sorted(grouped.values(), key=lambda e: -e["contract_value"])

    @staticmethod
    def _spend_by_project(company_id) -> dict[int, float]:
        """Recorded expense per project, for margin where a budget exists."""
        return {
            project_id: float(total or 0)
            for project_id, total in db.session.query(
                Transaction.project_id, func.sum(Transaction.amount)
            )
            .filter(
                Transaction.company_id == company_id,
                Transaction.transaction_type == TransactionType.EXPENSE,
            )
            .group_by(Transaction.project_id)
            .all()
        }

    @staticmethod
    def _band_performance(members: list, spend: dict[int, float]) -> dict:
        """Completion rate, mean duration and margin for one size band.

        Every figure is None rather than zero when nothing supports it. A band
        with no projects has no completion rate; saying 0% would read as a
        portfolio in trouble rather than a portfolio without data.
        """
        if not members:
            return {
                "count": 0,
                "avg_margin": None,
                "completion_rate": None,
                "avg_duration": None,
                "measured": False,
            }

        completed = [p for p in members if p.status == "completed"]

        durations = [
            (p.end_date - p.start_date).days / 30.44 for p in members if p.start_date and p.end_date
        ]

        # Margin is only meaningful once a project is finished. On work still in
        # flight, (budget - spend) / budget is budget *remaining*, and reporting
        # that as margin flatters a project that has simply not spent its money
        # yet — the demo project reads 86% "margin" four months into a two-year
        # job. The two are separated here.
        finished = [p for p in completed if p.budget and p.id in spend]
        finished_budget = sum(p.budget for p in finished)
        finished_cost = sum(spend[p.id] for p in finished)

        in_flight = [p for p in members if p.status != "completed" and p.budget and p.id in spend]
        in_flight_budget = sum(p.budget for p in in_flight)
        in_flight_cost = sum(spend[p.id] for p in in_flight)

        return {
            "count": len(members),
            "completion_rate": round(len(completed) / len(members) * 100, 1),
            "avg_duration": round(sum(durations) / len(durations), 1) if durations else None,
            # Realised margin, on finished work only.
            "avg_margin": (
                round((finished_budget - finished_cost) / finished_budget * 100, 1)
                if finished_budget
                else None
            ),
            "margin_basis": (
                f"{len(finished)} completed project(s) with a budget and recorded spend"
                if finished
                else "No completed project in this band has both a budget and recorded "
                "spend, so realised margin cannot be measured"
            ),
            # How much of the approved budget in-flight work has consumed.
            "budget_consumed_percent": (
                round(in_flight_cost / in_flight_budget * 100, 1) if in_flight_budget else None
            ),
            "measured": True,
        }

    @staticmethod
    def _by_location(projects: list, spend: dict[int, float]) -> list[dict]:
        """Portfolio grouped by the location recorded on each project.

        **Extension path:** this reads ``Project.location`` as free text, so a
        deployment gets a breakdown the moment locations are filled in. To
        group by region rather than by exact string, add a ``region`` column to
        ``Project`` and change the key below — the rest of the shape holds.
        """
        grouped: dict[str, dict] = {}
        for project in projects:
            key = (project.location or "").strip() or "Unspecified"
            entry = grouped.setdefault(
                key, {"region": key, "projects": 0, "contract_value": 0.0, "recorded_spend": 0.0}
            )
            entry["projects"] += 1
            entry["contract_value"] += float(project.budget or 0)
            entry["recorded_spend"] += spend.get(project.id, 0.0)

        for entry in grouped.values():
            entry["contract_value"] = round(entry["contract_value"], 2)
            entry["recorded_spend"] = round(entry["recorded_spend"], 2)

        return sorted(grouped.values(), key=lambda e: -e["contract_value"])

    @staticmethod
    def _ledger_totals(company_id) -> dict:
        """Income, expense and margin from recorded transactions.

        Returns ``measured: False`` and ``None`` figures when the ledger is
        empty, rather than zeros. Zero profit and unknown profit are different
        statements, and an executive dashboard must not confuse them.
        """
        totals = dict(
            db.session.query(Transaction.transaction_type, func.sum(Transaction.amount))
            .filter(Transaction.company_id == company_id)
            .group_by(Transaction.transaction_type)
            .all()
        )

        income = float(totals.get(TransactionType.INCOME) or 0)
        expense = float(totals.get(TransactionType.EXPENSE) or 0)

        # Invoices are revenue too, and a deployment may raise invoices without
        # posting income transactions. Take the larger of the two rather than
        # double counting.
        invoiced = float(
            db.session.query(func.coalesce(func.sum(Invoice.total_amount), 0))
            .filter(Invoice.company_id == company_id)
            .scalar()
            or 0
        )
        revenue = max(income, invoiced)

        if not revenue and not expense:
            return {
                "measured": False,
                "income": None,
                "expense": None,
                "profit": None,
                "margin_percent": None,
            }

        profit = revenue - expense
        return {
            "measured": True,
            "income": round(revenue, 2),
            "expense": round(expense, 2),
            "profit": round(profit, 2),
            "margin_percent": round(profit / revenue * 100, 1) if revenue else None,
        }

    @staticmethod
    def _budget_variance(company_id, projects) -> float | None:
        """Spend against approved budget, on completed projects only."""
        spend_by_project = dict(
            db.session.query(Transaction.project_id, func.sum(Transaction.amount))
            .filter(
                Transaction.company_id == company_id,
                Transaction.transaction_type == TransactionType.EXPENSE,
            )
            .group_by(Transaction.project_id)
            .all()
        )

        # Completed projects only. Spend under budget on a live project is work
        # not yet done, not a favourable variance, and averaging the two makes
        # an overrunning portfolio look healthy.
        finished = [
            p for p in projects if p.status == "completed" and p.budget and p.id in spend_by_project
        ]
        budget = sum(p.budget for p in finished)
        spend = sum(float(spend_by_project[p.id]) for p in finished)

        if not budget:
            return None
        return round((spend - budget) / budget * 100, 1)

    @staticmethod
    def _fleet_utilization(company_id) -> float:
        """Mean 30-day utilisation across a company's active equipment."""
        fleet = Equipment.query.filter_by(company_id=company_id, is_active=True).all()
        if not fleet:
            return 0.0
        return round(sum(item.utilization_rate(30) for item in fleet) / len(fleet), 1)

    @staticmethod
    def _grade_overdue(overdue: int, total: int) -> str:
        if total == 0:
            return "unknown"
        share = overdue / total
        if share == 0:
            return "low"
        if share <= 0.15:
            return "medium"
        return "high"

    def get_financial_performance(self, company_id, months=12):
        """Monthly revenue, cost and margin, aggregated from the ledger.

        This used to generate the whole series::

            base_revenue = 2500000
            growth_factor = 1 + (i * 0.02)
            variance = 0.8 + (i % 3) * 0.1
            revenue = base_revenue * growth_factor * variance
            costs = revenue * 0.75

        Twelve months of invented revenue on a two-percent growth curve, the
        same for every company, carrying a ``simulated`` flag that the UI was
        free to ignore. It is measured now.

        Where the ledger is empty the series is empty and ``available`` is
        False, with the reason stated. **Extension path:** nothing further is
        needed in this module — post ``Transaction`` rows of type INCOME or
        EXPENSE with a ``transaction_date``, or raise ``Invoice`` records, and
        every figure below populates. That is the whole contract.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=31 * months)

        # Bucketed in Python, not with func.strftime: that is SQLite-only and
        # would have worked in development and failed on the PostgreSQL this
        # deploys to. date_trunc and to_char are the Postgres spellings and
        # neither exists in SQLite, so there is no portable SQL form.
        rows = (
            db.session.query(
                Transaction.transaction_date,
                Transaction.transaction_type,
                Transaction.amount,
            )
            .filter(
                Transaction.company_id == company_id,
                Transaction.transaction_date >= start_date,
            )
            .all()
        )

        buckets: dict[str, dict[str, float]] = {}
        for transaction_date, kind, amount in rows:
            if transaction_date is None:
                continue
            month = transaction_date.strftime("%Y-%m")
            bucket = buckets.setdefault(month, {"revenue": 0.0, "costs": 0.0})
            if kind == TransactionType.INCOME:
                bucket["revenue"] += float(amount or 0)
            elif kind == TransactionType.EXPENSE:
                bucket["costs"] += float(amount or 0)

        # Invoices count as revenue in months where no income was posted, so a
        # deployment that invoices without keeping a ledger still gets a trend.
        invoiced_by_month: dict[str, float] = {}
        for issue_date, total in (
            db.session.query(Invoice.issue_date, Invoice.total_amount)
            .filter(Invoice.company_id == company_id, Invoice.issue_date >= start_date)
            .all()
        ):
            if issue_date is None:
                continue
            month = issue_date.strftime("%Y-%m")
            invoiced_by_month[month] = invoiced_by_month.get(month, 0.0) + float(total or 0)

        for month, invoiced in invoiced_by_month.items():
            bucket = buckets.setdefault(month, {"revenue": 0.0, "costs": 0.0})
            bucket["revenue"] = max(bucket["revenue"], invoiced)

        if not buckets:
            return {
                "available": False,
                "reason": (
                    "No income, expense or invoice records in the last "
                    f"{months} months, so there is no financial trend to report."
                ),
                "how_to_populate": (
                    "Record Transaction rows of type INCOME or EXPENSE against projects, "
                    "or raise Invoices. This report reads them directly; no configuration "
                    "or code change is required."
                ),
                "monthly_trends": [],
                "year_to_date": None,
            }

        monthly_trends = []
        for month in sorted(buckets):
            revenue = round(buckets[month]["revenue"], 2)
            costs = round(buckets[month]["costs"], 2)
            profit = round(revenue - costs, 2)
            monthly_trends.append(
                {
                    "month": month,
                    "revenue": revenue,
                    "costs": costs,
                    "profit": profit,
                    "margin": round(profit / revenue * 100, 1) if revenue else None,
                }
            )

        total_revenue = sum(m["revenue"] for m in monthly_trends)
        total_profit = sum(m["profit"] for m in monthly_trends)

        return {
            "available": True,
            "months_with_data": len(monthly_trends),
            "monthly_trends": monthly_trends,
            "year_to_date": {
                "revenue": round(total_revenue, 2),
                "profit": round(total_profit, 2),
                "margin": round(total_profit / total_revenue * 100, 1) if total_revenue else None,
            },
        }

    def get_project_portfolio_analysis(self, company_id):
        """Analyse project portfolio performance.

        Everything here is measured. Size bands, completion rates, durations,
        margins, the geographic split and the sector split all come from
        projects and transactions. Figures that nothing supports are ``None``,
        not zero — a band with no data and a band at zero percent are different
        statements and an executive dashboard must not merge them.
        """
        projects = Project.query.filter_by(company_id=company_id).all()

        # Categorize projects by size
        small_projects = []  # < $500K
        medium_projects = []  # $500K - $5M
        large_projects = []  # > $5M

        for project in projects:
            if project.budget:
                if project.budget < 500000:
                    small_projects.append(project)
                elif project.budget < 5000000:
                    medium_projects.append(project)
                else:
                    large_projects.append(project)

        # Completion rate, duration and margin per band, all measured. These
        # were constants — small projects always 15.2% margin, 95.8% complete,
        # 3.2 months, for every company that ever loaded the page.
        spend = self._spend_by_project(company_id)
        performance_by_size = {
            band: self._band_performance(members, spend)
            for band, members in (
                ("small", small_projects),
                ("medium", medium_projects),
                ("large", large_projects),
            )
        }

        # Grouped by the location recorded on each project. This was four
        # hardcoded US regions with invented project counts and revenue —
        # figures that did not move when the portfolio did.
        geographic_data = self._by_location(projects, spend)

        return {
            "portfolio_summary": {
                "total_projects": len(projects),
                "total_value": sum(p.budget for p in projects if p.budget),
                "avg_project_size": sum(p.budget for p in projects if p.budget)
                / len([p for p in projects if p.budget])
                if projects
                else 0,
            },
            "performance_by_size": performance_by_size,
            "geographic_distribution": geographic_data,
            "sector_analysis": self._by_sector(projects, spend),
        }

    def get_operational_efficiency(self, company_id):
        """Calculate operational efficiency metrics"""
        projects = Project.query.filter_by(company_id=company_id).all()

        # Calculate schedule performance
        on_time_projects = 0
        total_evaluated = 0

        for project in projects:
            if project.status == "completed" and project.end_date:
                total_evaluated += 1
                # Simplified: assume on-time if completed
                on_time_projects += 1

        schedule_performance = (
            (on_time_projects / total_evaluated * 100) if total_evaluated > 0 else 0
        )

        # Resource efficiency metrics
        efficiency_metrics = {
            "schedule_performance": {
                "on_time_completion": schedule_performance,
                "average_delay": 2.3,  # days
                "critical_path_accuracy": 87.5,
            },
            "cost_performance": {
                "budget_adherence": 94.2,
                "cost_variance": -1.8,  # Under budget
                "change_order_rate": 8.3,
            },
            "quality_metrics": {
                "defect_rate": 0.8,  # per 1000 tasks
                "rework_percentage": 2.1,
                "client_satisfaction": 4.7,  # out of 5
            },
            "productivity_indicators": {
                "tasks_per_day": 12.4,
                "utilization_rate": 78.9,
                "efficiency_score": 91.2,
            },
        }

        return efficiency_metrics

    def get_risk_assessment(self, company_id):
        """Comprehensive risk assessment"""
        projects = Project.query.filter_by(company_id=company_id).all()

        # Calculate various risk factors
        financial_risk = "Low"  # Based on cash flow, receivables, etc.
        operational_risk = "Medium"  # Based on resource availability, capacity
        market_risk = "Low"  # Based on market conditions, competition

        # Project-specific risks
        high_risk_projects = []
        medium_risk_projects = []

        for project in projects:
            risk_score = self._calculate_project_risk(project)
            if risk_score > 7:
                high_risk_projects.append(
                    {
                        "id": project.id,
                        "name": project.name,
                        "risk_score": risk_score,
                        "risk_factors": ["Schedule delay", "Budget overrun"],
                    }
                )
            elif risk_score > 4:
                medium_risk_projects.append(
                    {
                        "id": project.id,
                        "name": project.name,
                        "risk_score": risk_score,
                        "risk_factors": ["Resource constraints"],
                    }
                )

        return {
            "overall_risk_level": "Medium",
            "risk_categories": {
                "financial": financial_risk,
                "operational": operational_risk,
                "market": market_risk,
                "regulatory": "Low",
            },
            "project_risks": {
                "high_risk": high_risk_projects,
                "medium_risk": medium_risk_projects,
                "mitigation_recommendations": [
                    "Increase buffer time for critical path tasks",
                    "Diversify supplier base to reduce supply chain risk",
                    "Implement more frequent progress reviews",
                    "Enhance cash flow monitoring",
                ],
            },
            "risk_trends": {
                "improving": ["Cost management", "Quality control"],
                "stable": ["Schedule adherence", "Resource planning"],
                "attention_needed": ["Vendor management", "Weather contingency"],
            },
        }

    def _calculate_project_risk(self, project):
        """Calculate risk score for individual project"""
        risk_score = 5  # Base score

        # Adjust based on project characteristics
        if project.budget and project.budget > 5000000:
            risk_score += 1  # Large projects have higher risk

        if project.end_date and project.end_date < date.today() and project.status != "completed":
            risk_score += 3  # Overdue projects are high risk

        # Add other risk factors as needed
        return min(risk_score, 10)  # Cap at 10


# Executive dashboard instance
executive_dashboard = ExecutiveDashboard()


@executive_bp.route("/executive")
@login_required
def executive_dashboard_page():
    """Executive dashboard main page"""
    # Check if user has executive access
    if current_user.role.name not in ["ADMIN"]:
        from flask import flash, redirect, url_for

        flash("Access denied. Executive privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    return render_template("executive/dashboard.html")


@executive_bp.route("/api/executive/overview")
@login_required
def api_company_overview():
    """API endpoint for company overview"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    date_range = request.args.get("days", 30, type=int)
    overview = executive_dashboard.get_company_overview(current_user.company_id, date_range)

    return jsonify(overview)


@executive_bp.route("/api/executive/financial")
@login_required
def api_financial_performance():
    """API endpoint for financial performance"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    months = request.args.get("months", 12, type=int)
    financial_data = executive_dashboard.get_financial_performance(current_user.company_id, months)

    return jsonify(financial_data)


@executive_bp.route("/api/executive/portfolio")
@login_required
def api_portfolio_analysis():
    """API endpoint for portfolio analysis"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    portfolio_data = executive_dashboard.get_project_portfolio_analysis(current_user.company_id)

    return jsonify(portfolio_data)


@executive_bp.route("/api/executive/efficiency")
@login_required
def api_operational_efficiency():
    """API endpoint for operational efficiency"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    efficiency_data = executive_dashboard.get_operational_efficiency(current_user.company_id)

    return jsonify(efficiency_data)


@executive_bp.route("/api/executive/risk")
@login_required
def api_risk_assessment():
    """API endpoint for risk assessment"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    risk_data = executive_dashboard.get_risk_assessment(current_user.company_id)

    return jsonify(risk_data)
