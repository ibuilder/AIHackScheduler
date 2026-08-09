"""The executive dashboard reports what happened, or says it cannot.

This was the last facade. Twelve months of revenue were generated from a
constant::

    base_revenue = 2500000
    growth_factor = 1 + (i * 0.02)
    revenue = base_revenue * growth_factor * variance
    costs = revenue * 0.75

along with a 12% profit margin, a 5% budget variance, four hardcoded US regions
with invented project counts, four sectors with invented margins, and per-size
performance bands where small projects were always 15.2% margin and 95.8%
complete. Identical for every company, unmoved by anything anyone did. A
``simulated`` flag was attached, which a chart is free to ignore.

Everything is measured now, and where nothing supports a figure it is ``None``
with the reason stated — never zero. Zero profit and unknown profit are
different statements, and the whole point of this page is that someone acts on
what it says.
"""

from datetime import date, timedelta

import pytest

from extensions import db
from models import Company, Invoice, InvoiceStatus, Transaction, TransactionType


@pytest.fixture
def dashboard():
    from reports.executive_dashboard import ExecutiveDashboard

    return ExecutiveDashboard()


@pytest.fixture
def empty_company(app_context):
    """A company with no projects, transactions or invoices at all."""
    company = Company(name="Brand New Contractors")
    db.session.add(company)
    db.session.commit()
    return company


def _expense(project, amount, when, company_id, number):
    db.session.add(
        Transaction(
            transaction_number=number,
            transaction_type=TransactionType.EXPENSE,
            amount=amount,
            description="Test expense",
            transaction_date=when,
            project_id=project.id,
            company_id=company_id,
            created_by_id=project.created_by,
        )
    )


def _income(project, amount, when, company_id, number):
    db.session.add(
        Transaction(
            transaction_number=number,
            transaction_type=TransactionType.INCOME,
            amount=amount,
            description="Test income",
            transaction_date=when,
            project_id=project.id,
            company_id=company_id,
            created_by_id=project.created_by,
        )
    )


# ── nothing recorded ─────────────────────────────────────────────────────


def test_no_ledger_means_no_trend_rather_than_a_generated_one(dashboard, empty_company):
    result = dashboard.get_financial_performance(empty_company.id)

    assert result["available"] is False
    assert result["monthly_trends"] == []
    assert result["year_to_date"] is None
    # And it says what to do about it.
    assert "Transaction" in result["how_to_populate"]


def test_no_ledger_means_margin_is_unknown_not_zero(dashboard, empty_company):
    """A zero margin reads as a company breaking even. An unknown margin reads
    as a company that has not recorded anything. They must not be confused."""
    financial = dashboard.get_company_overview(empty_company.id)["financial"]

    assert financial["measured"] is False
    assert financial["profit_margin"] is None
    assert financial["estimated_profit"] is None
    assert financial["recorded_income"] is None
    assert financial["note"] is not None


def test_the_generated_series_is_gone(dashboard, seeded):
    """The old implementation always produced exactly `months` entries from a
    2,500,000 base. A real ledger produces one entry per month that has data."""
    result = dashboard.get_financial_performance(seeded.company_id, months=12)

    assert result["available"] is True
    assert len(result["monthly_trends"]) < 12, "12 entries suggests a generated series"
    assert all(m["revenue"] != 2500000 for m in result["monthly_trends"])


# ── measured from the ledger ─────────────────────────────────────────────


def test_monthly_trends_come_from_transactions(dashboard, seeded):
    company_id = seeded.company_id
    when = date.today().replace(day=15)

    _income(seeded, 400000, when, company_id, "TXN-IN-1")
    _expense(seeded, 250000, when, company_id, "TXN-EX-1")
    db.session.commit()

    result = dashboard.get_financial_performance(company_id)
    month = when.strftime("%Y-%m")
    entry = next(m for m in result["monthly_trends"] if m["month"] == month)

    assert entry["revenue"] >= 400000
    assert entry["costs"] >= 250000
    assert entry["profit"] == round(entry["revenue"] - entry["costs"], 2)


def test_an_invoice_counts_as_revenue_without_an_income_transaction(dashboard, seeded):
    """A deployment may invoice without keeping a ledger; it still gets a trend."""
    when = date.today().replace(day=10)
    db.session.add(
        Invoice(
            invoice_number="INV-EXEC-1",
            client_name="Acme",
            issue_date=when,
            due_date=when + timedelta(days=30),
            subtotal=750000,
            total_amount=750000,
            status=InvoiceStatus.SENT,
            project_id=seeded.id,
            company_id=seeded.company_id,
            created_by_id=seeded.created_by,
        )
    )
    db.session.commit()

    result = dashboard.get_financial_performance(seeded.company_id)
    entry = next(m for m in result["monthly_trends"] if m["month"] == when.strftime("%Y-%m"))
    assert entry["revenue"] >= 750000


def test_income_and_invoices_are_not_double_counted(dashboard, seeded):
    """Both are revenue. Adding them together would report twice the money."""
    when = date.today().replace(day=12)
    _income(seeded, 500000, when, seeded.company_id, "TXN-IN-2")
    db.session.add(
        Invoice(
            invoice_number="INV-EXEC-2",
            client_name="Acme",
            issue_date=when,
            due_date=when + timedelta(days=30),
            subtotal=500000,
            total_amount=500000,
            status=InvoiceStatus.SENT,
            project_id=seeded.id,
            company_id=seeded.company_id,
            created_by_id=seeded.created_by,
        )
    )
    db.session.commit()

    result = dashboard.get_financial_performance(seeded.company_id)
    entry = next(m for m in result["monthly_trends"] if m["month"] == when.strftime("%Y-%m"))
    assert entry["revenue"] < 1000000, "income and invoices were summed instead of reconciled"


# ── margin is not budget remaining ───────────────────────────────────────


def test_an_unfinished_project_reports_budget_consumed_not_margin(dashboard, seeded):
    """The trap this page was built to avoid. The demo project is four months
    into a two-year job with 14% of its budget spent. Reported as margin that
    is "86% profitable" — the least advanced project looks like the best one."""
    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    band = analysis["performance_by_size"]["large"]

    assert band["avg_margin"] is None
    assert "no completed project" in band["margin_basis"].lower()
    assert band["budget_consumed_percent"] is not None
    assert 0 < band["budget_consumed_percent"] < 100


def test_a_completed_project_does_report_realised_margin(dashboard, seeded):
    seeded.status = "completed"
    db.session.commit()

    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    band = analysis["performance_by_size"]["large"]

    assert band["avg_margin"] is not None
    assert band["completion_rate"] == 100.0


def test_budget_variance_ignores_work_still_in_flight(dashboard, seeded):
    """Underspend on a live project is work not yet done. Averaging it with
    completed work makes an overrunning portfolio look healthy."""
    financial = dashboard.get_company_overview(seeded.company_id)["financial"]
    assert financial["budget_variance"] is None

    seeded.status = "completed"
    db.session.commit()
    financial = dashboard.get_company_overview(seeded.company_id)["financial"]
    assert financial["budget_variance"] is not None


# ── geography and sector come from the projects ──────────────────────────


def test_geography_is_grouped_from_recorded_locations(dashboard, seeded):
    """Was four hardcoded US regions with invented counts and revenue."""
    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    regions = {entry["region"] for entry in analysis["geographic_distribution"]}

    assert seeded.location in regions
    assert regions != {"Northeast", "Southeast", "Midwest", "West"}


def test_a_project_without_a_location_is_unspecified_not_invented(dashboard, seeded):
    seeded.location = None
    db.session.commit()

    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    assert [e["region"] for e in analysis["geographic_distribution"]] == ["Unspecified"]


def test_sector_comes_from_the_template_the_project_was_created_from(dashboard, seeded):
    seeded.template_used = "industrial_warehouse"
    db.session.commit()

    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    sectors = {entry["sector"] for entry in analysis["sector_analysis"]}
    assert sectors == {"Industrial"}


def test_a_project_from_no_template_is_unspecified(dashboard, seeded):
    """Rather than assigned to whichever sector looks plausible."""
    seeded.template_used = None
    db.session.commit()

    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    assert [e["sector"] for e in analysis["sector_analysis"]] == ["Unspecified"]


def test_an_empty_band_reports_nothing_rather_than_zero(dashboard, seeded):
    """A band with no projects has no completion rate. Reporting 0% would read
    as a portfolio in trouble rather than a portfolio without data."""
    analysis = dashboard.get_project_portfolio_analysis(seeded.company_id)
    small = analysis["performance_by_size"]["small"]

    assert small["count"] == 0
    assert small["measured"] is False
    assert small["completion_rate"] is None
    assert small["avg_margin"] is None


# ── the payload no longer claims to be simulated ─────────────────────────


def test_nothing_is_flagged_simulated_any_more(dashboard, seeded):
    """The flags existed because the data was invented. Their absence is the
    claim that it no longer is."""
    company_id = seeded.company_id
    payloads = [
        dashboard.get_company_overview(company_id),
        dashboard.get_financial_performance(company_id),
        dashboard.get_project_portfolio_analysis(company_id),
    ]
    for payload in payloads:
        assert "simulated" not in payload
        assert "partially_simulated" not in payload
        assert "simulated_note" not in payload


def test_the_source_computes_rather_than_asserts_the_numbers():
    """The specific values the old implementation returned.

    Checked against the AST, not the raw text: the docstrings above quote the
    removed code on purpose, so a substring search would match its own
    explanation of what was deleted.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "reports" / "executive_dashboard.py"
    ).read_text(encoding="utf-8")

    invented = {2500000, 8500000, 18500000, 6200000, 11200000, 9800000, 15.2, 95.8, 78.5, 8.9, 12.1}

    found = set()
    for node in ast.walk(ast.parse(source)):
        # A number that appears as a literal in executable code. Docstrings are
        # str constants and never match a numeric comparison.
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value in invented:
                found.add(node.value)

    assert not found, f"still hardcoded in executable code: {sorted(found)}"


def test_every_dashboard_endpoint_answers(signed_in):
    client, _, _ = signed_in
    for url in (
        "/api/executive/overview",
        "/api/executive/financial",
        "/api/executive/portfolio",
        "/api/executive/efficiency",
        "/api/executive/risk",
    ):
        response = client.get(url)
        # 403 is a legitimate answer for a non-executive role; a 500 is not.
        assert response.status_code < 500, (
            f"{url} -> {response.status_code}: {response.get_data(as_text=True)[:160]}"
        )
