"""Tests for payment recording and invoice balances.

This is bookkeeping, not card processing — nothing here touches a payment
network. What it must get right is that a balance always equals the total minus
what actually cleared, and that status follows from the numbers.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from extensions import db
from models import Company, Invoice, InvoiceStatus, PaymentMethod, PaymentStatus
from services.billing import (
    BillingError,
    aged_receivables,
    record_payment,
    refresh_overdue,
    to_amount,
    void_payment,
)


@pytest.fixture
def company(app_context):
    company = Company(name="Billing Test Co")
    db.session.add(company)
    db.session.flush()
    return company


def _invoice(company, total="1000.00", status=InvoiceStatus.SENT, due_in_days=30, user_id=None):
    from models import User

    if user_id is None:
        seq = User.query.count() + 1
        user = User(
            username=f"biller{company.id}-{seq}",
            email=f"biller{company.id}-{seq}@example.com",
            password_hash="x",
            first_name="Bill",
            last_name="Er",
            company_id=company.id,
        )
        db.session.add(user)
        db.session.flush()
        user_id = user.id

    invoice = Invoice(
        invoice_number=f"INV-{Invoice.query.count() + 1:04d}",
        client_name="Acme Developments",
        client_email="ap@acme.example",
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=due_in_days),
        subtotal=Decimal(total),
        total_amount=Decimal(total),
        status=status,
        company_id=company.id,
        created_by_id=user_id,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def _pay(invoice, amount, company, **kwargs):
    return record_payment(
        invoice,
        amount,
        payment_date=kwargs.pop("payment_date", date.today()),
        method=kwargs.pop("method", PaymentMethod.BANK_TRANSFER),
        company_id=company.id,
        **kwargs,
    )


# ── amount parsing ────────────────────────────────────────────────────────


def test_amount_must_be_positive():
    with pytest.raises(BillingError, match="greater than zero"):
        to_amount("0")
    with pytest.raises(BillingError, match="greater than zero"):
        to_amount("-50")


def test_amount_rejects_nonsense():
    with pytest.raises(BillingError, match="not a valid amount"):
        to_amount("twenty quid")


def test_amount_is_rounded_to_cents():
    assert to_amount("10.005") == Decimal("10.01")


# ── recording payments ────────────────────────────────────────────────────


def test_a_payment_reduces_the_balance(company):
    invoice = _invoice(company, "1000.00")
    _pay(invoice, "400.00", company)

    assert invoice.amount_paid == Decimal("400.00")
    assert invoice.balance_due == Decimal("600.00")
    assert invoice.status is InvoiceStatus.PARTIAL


def test_paying_in_full_settles_the_invoice(company):
    invoice = _invoice(company, "1000.00")
    _pay(invoice, "1000.00", company)

    assert invoice.is_settled is True
    assert invoice.balance_due == Decimal("0.00")
    assert invoice.status is InvoiceStatus.PAID


def test_several_part_payments_settle_the_invoice(company):
    invoice = _invoice(company, "900.00")
    _pay(invoice, "300.00", company)
    _pay(invoice, "300.00", company)
    assert invoice.status is InvoiceStatus.PARTIAL

    _pay(invoice, "300.00", company)
    assert invoice.status is InvoiceStatus.PAID
    assert invoice.balance_due == Decimal("0.00")


def test_the_cached_total_matches_the_payment_rows(company):
    """paid_amount is stored for query speed but derived from the rows; the
    two must never disagree."""
    invoice = _invoice(company, "1000.00")
    _pay(invoice, "250.00", company)
    _pay(invoice, "125.50", company)

    assert invoice.paid_amount == invoice.amount_paid == Decimal("375.50")


def test_overpayment_is_refused_by_default(company):
    """Almost always a typo, so it needs saying out loud."""
    invoice = _invoice(company, "500.00")

    with pytest.raises(BillingError, match="exceeds the outstanding balance"):
        _pay(invoice, "600.00", company)


def test_overpayment_is_allowed_when_asked_for(company):
    invoice = _invoice(company, "500.00")
    _pay(invoice, "600.00", company, allow_overpayment=True)

    assert invoice.balance_due == Decimal("-100.00")
    assert invoice.status is InvoiceStatus.PAID


def test_future_dated_payments_are_refused(company):
    invoice = _invoice(company, "500.00")

    with pytest.raises(BillingError, match="cannot be in the future"):
        _pay(invoice, "100.00", company, payment_date=date.today() + timedelta(days=1))


def test_cannot_pay_a_draft_invoice(company):
    invoice = _invoice(company, "500.00", status=InvoiceStatus.DRAFT)

    with pytest.raises(BillingError, match="Send the invoice"):
        _pay(invoice, "100.00", company)


def test_cannot_pay_a_cancelled_invoice(company):
    invoice = _invoice(company, "500.00", status=InvoiceStatus.CANCELLED)

    with pytest.raises(BillingError, match="cancelled invoice"):
        _pay(invoice, "100.00", company)


def test_payment_numbers_are_sequential_per_company(company):
    invoice = _invoice(company, "1000.00")
    first = _pay(invoice, "100.00", company)
    second = _pay(invoice, "100.00", company)

    assert first.payment_number.endswith("0001")
    assert second.payment_number.endswith("0002")


# ── voiding ───────────────────────────────────────────────────────────────


def test_voiding_restores_the_balance(company):
    invoice = _invoice(company, "1000.00")
    payment = _pay(invoice, "1000.00", company)
    assert invoice.status is InvoiceStatus.PAID

    void_payment(payment, reason="Recorded against the wrong invoice")

    assert invoice.balance_due == Decimal("1000.00")
    assert invoice.amount_paid == Decimal("0.00")
    assert invoice.status is not InvoiceStatus.PAID


def test_voided_payments_are_kept_for_the_audit_trail(company):
    from models import Payment

    invoice = _invoice(company, "500.00")
    payment = _pay(invoice, "500.00", company)
    void_payment(payment, reason="Duplicate")

    assert Payment.query.count() == 1
    assert Payment.query.first().status is PaymentStatus.CANCELLED
    assert "Duplicate" in Payment.query.first().failure_reason


def test_voiding_twice_is_refused(company):
    invoice = _invoice(company, "500.00")
    payment = _pay(invoice, "500.00", company)
    void_payment(payment)

    with pytest.raises(BillingError, match="already voided"):
        void_payment(payment)


def test_only_cleared_payments_count_toward_the_balance(company):
    invoice = _invoice(company, "1000.00")
    keep = _pay(invoice, "400.00", company)
    drop = _pay(invoice, "300.00", company)
    void_payment(drop)

    assert invoice.amount_paid == keep.amount == Decimal("400.00")


# ── status derivation ─────────────────────────────────────────────────────


def test_an_unpaid_invoice_past_its_due_date_becomes_overdue(company):
    invoice = _invoice(company, "500.00", due_in_days=-10)

    assert invoice.derive_status() is InvoiceStatus.OVERDUE
    assert invoice.days_overdue == 10


def test_a_draft_never_becomes_overdue(company):
    """An invoice nobody has sent cannot be late."""
    invoice = _invoice(company, "500.00", status=InvoiceStatus.DRAFT, due_in_days=-30)

    assert invoice.derive_status() is InvoiceStatus.DRAFT
    assert invoice.days_overdue == 0


def test_a_settled_invoice_is_never_overdue(company):
    invoice = _invoice(company, "500.00", due_in_days=-30)
    _pay(invoice, "500.00", company)

    assert invoice.status is InvoiceStatus.PAID
    assert invoice.days_overdue == 0


def test_refresh_overdue_updates_stale_statuses(company):
    _invoice(company, "500.00", due_in_days=-5)
    _invoice(company, "500.00", due_in_days=-40)
    _invoice(company, "500.00", due_in_days=30)

    assert refresh_overdue(company.id) == 2

    overdue = Invoice.query.filter_by(status=InvoiceStatus.OVERDUE).count()
    assert overdue == 2


# ── aged receivables ──────────────────────────────────────────────────────


def test_aged_receivables_bucket_by_days_overdue(company):
    _invoice(company, "100.00", due_in_days=30)  # current
    _invoice(company, "200.00", due_in_days=-10)  # 1-30
    _invoice(company, "300.00", due_in_days=-45)  # 31-60
    _invoice(company, "400.00", due_in_days=-75)  # 61-90
    _invoice(company, "500.00", due_in_days=-200)  # over 90

    report = aged_receivables(company.id)

    assert report["buckets"]["current"] == 100.0
    assert report["buckets"]["1_30"] == 200.0
    assert report["buckets"]["31_60"] == 300.0
    assert report["buckets"]["61_90"] == 400.0
    assert report["buckets"]["over_90"] == 500.0
    assert report["total_outstanding"] == 1500.0


def test_settled_invoices_are_excluded_from_receivables(company):
    invoice = _invoice(company, "500.00", due_in_days=-40)
    _pay(invoice, "500.00", company)

    report = aged_receivables(company.id)
    assert report["total_outstanding"] == 0.0


def test_part_paid_invoices_report_only_the_remaining_balance(company):
    invoice = _invoice(company, "1000.00", due_in_days=-40)
    _pay(invoice, "600.00", company)

    report = aged_receivables(company.id)
    assert report["buckets"]["31_60"] == 400.0


# ── the financial module end to end ───────────────────────────────────────


def test_every_financial_page_loads(signed_in):
    """Four of these routes queried Project.is_active, a column that does not
    exist, so they raised InvalidRequestError and returned 500."""
    client, _, _ = signed_in

    for path in (
        "/financial",
        "/transactions",
        "/transactions/create",
        "/invoices",
        "/invoices/create",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_recording_a_payment_through_the_form(signed_in, app_context):
    from models import Invoice, User

    client, project, _ = signed_in
    user = User.query.filter_by(username="demo").first()
    invoice = _invoice_for(user, project)

    response = client.post(
        f"/invoices/{invoice.id}/payments",
        data={
            "amount": "250.00",
            "payment_date": date.today().isoformat(),
            "payment_method": "bank_transfer",
            "reference_number": "FT-9931",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    refreshed = Invoice.query.get(invoice.id)
    assert refreshed.amount_paid == Decimal("250.00")
    assert refreshed.status is InvoiceStatus.PARTIAL


def test_the_form_refuses_an_overpayment(signed_in, app_context):
    from models import Invoice, User

    client, project, _ = signed_in
    user = User.query.filter_by(username="demo").first()
    invoice = _invoice_for(user, project)

    client.post(
        f"/invoices/{invoice.id}/payments",
        data={
            "amount": "99999.00",
            "payment_date": date.today().isoformat(),
            "payment_method": "cash",
        },
        follow_redirects=True,
    )

    assert Invoice.query.get(invoice.id).amount_paid == Decimal("0")


def test_aged_receivables_endpoint(signed_in, app_context):
    """The seeded demo already carries a part-paid application for payment,
    so this asserts the delta rather than an absolute total."""
    from models import User

    client, project, _ = signed_in
    user = User.query.filter_by(username="demo").first()

    before = client.get("/api/financial/aged-receivables").get_json()
    _invoice_for(user, project, due_in_days=-45)
    after = client.get("/api/financial/aged-receivables").get_json()

    assert after["buckets"]["31_60"] - before["buckets"]["31_60"] == 1000.0
    assert after["total_outstanding"] - before["total_outstanding"] == 1000.0
    assert after["invoice_count"] == before["invoice_count"] + 1


def _invoice_for(user, project, due_in_days=30):
    invoice = Invoice(
        invoice_number=f"INV-{Invoice.query.count() + 1:04d}",
        client_name="Acme Developments",
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=due_in_days),
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.SENT,
        project_id=project.id,
        company_id=user.company_id,
        created_by_id=user.id,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice
