"""Recording payments against invoices.

This is bookkeeping, not payment processing. Nothing here talks to a card
network: it records money the business has already received and keeps invoice
balances and statuses consistent with those records.

The repository previously advertised "Stripe integration in progress" with no
implementation of any kind. Taking card details is a different problem with
different obligations — key management, webhook reconciliation, PCI scope —
and is deliberately not attempted here.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func

from extensions import db
from models import Invoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus


class BillingError(ValueError):
    """A payment could not be recorded as asked."""


def to_amount(value) -> Decimal:
    """Parse a money value, rejecting anything that is not a positive number."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BillingError(f"{value!r} is not a valid amount") from exc

    if amount <= 0:
        raise BillingError("Payment amount must be greater than zero")

    # Half-up, not Python's default half-even. Banker's rounding is right for
    # statistics and wrong for money: a customer paying 10.005 expects 10.01.
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def next_payment_number(company_id: int) -> str:
    """Sequential per company, matching the invoice numbering convention."""
    year = date.today().year
    prefix = f"PAY-{year}-"
    highest = (
        db.session.query(func.max(Payment.payment_number))
        .filter(
            Payment.company_id == company_id,
            Payment.payment_number.like(f"{prefix}%"),
        )
        .scalar()
    )
    sequence = 1
    if highest:
        try:
            sequence = int(highest.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            sequence = 1
    return f"{prefix}{sequence:04d}"


def record_payment(
    invoice: Invoice,
    amount,
    *,
    payment_date: date,
    method: PaymentMethod,
    company_id: int,
    reference: str = "",
    payer_name: str = "",
    processed_by_id: int | None = None,
    notes: str = "",
    allow_overpayment: bool = False,
) -> Payment:
    """Record a cleared payment and bring the invoice's balance up to date."""
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BillingError("Cannot record a payment against a cancelled invoice")
    if invoice.status == InvoiceStatus.DRAFT:
        raise BillingError("Send the invoice before recording a payment against it")

    amount = to_amount(amount)

    if payment_date > date.today():
        raise BillingError("Payment date cannot be in the future")

    # Overpayment is usually a typo, so it is refused unless the caller says
    # otherwise — a credit balance is a decision, not a side effect.
    if not allow_overpayment and amount > invoice.balance_due:
        raise BillingError(
            f"Payment of {amount} exceeds the outstanding balance of {invoice.balance_due}"
        )

    payment = Payment(
        payment_number=next_payment_number(company_id),
        amount=amount,
        currency="USD",
        payment_date=payment_date,
        payment_method=method,
        status=PaymentStatus.COMPLETED,
        reference_number=(reference or None),
        payer_name=payer_name or invoice.client_name,
        payer_email=invoice.client_email,
        description=notes or f"Payment against {invoice.invoice_number}",
        company_id=company_id,
        processed_by_id=processed_by_id,
    )
    # Assign through the relationship, not the foreign key. Setting invoice_id
    # alone leaves invoice.payments holding its already-loaded list, so the
    # recalculation below would not see this payment and the invoice would
    # stay on its old status until something else expired the session.
    payment.invoice = invoice
    db.session.add(payment)
    db.session.flush()

    invoice.recalculate_payments()
    db.session.commit()
    return payment


def void_payment(payment: Payment, reason: str = "") -> Payment:
    """Reverse a payment recorded in error, keeping the row for the audit trail."""
    if payment.status == PaymentStatus.CANCELLED:
        raise BillingError("Payment is already voided")

    payment.status = PaymentStatus.CANCELLED
    payment.failure_reason = reason or "Voided"

    if payment.invoice:
        payment.invoice.recalculate_payments()
    db.session.commit()
    return payment


def refresh_overdue(company_id: int) -> int:
    """Move newly-overdue invoices into that status. Returns the count changed.

    Overdue is a function of the date, so it cannot be set once and left; an
    invoice becomes overdue while nobody is looking at it.
    """
    candidates = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.status.in_(
            [
                InvoiceStatus.SENT,
                InvoiceStatus.VIEWED,
                InvoiceStatus.PARTIAL,
                InvoiceStatus.OVERDUE,
            ]
        ),
    ).all()

    changed = 0
    for invoice in candidates:
        derived = invoice.derive_status()
        if derived != invoice.status:
            invoice.status = derived
            changed += 1

    if changed:
        db.session.commit()
    return changed


def aged_receivables(company_id: int) -> dict:
    """Outstanding balances bucketed by how long they have been overdue."""
    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "over_90": 0.0}

    open_invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.status.notin_([InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED, InvoiceStatus.PAID]),
    ).all()

    for invoice in open_invoices:
        balance = float(invoice.balance_due)
        if balance <= 0:
            continue
        overdue = invoice.days_overdue
        if overdue == 0:
            buckets["current"] += balance
        elif overdue <= 30:
            buckets["1_30"] += balance
        elif overdue <= 60:
            buckets["31_60"] += balance
        elif overdue <= 90:
            buckets["61_90"] += balance
        else:
            buckets["over_90"] += balance

    return {
        "buckets": {name: round(value, 2) for name, value in buckets.items()},
        "total_outstanding": round(sum(buckets.values()), 2),
        "invoice_count": len(open_invoices),
    }
