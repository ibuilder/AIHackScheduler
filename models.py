import enum
from datetime import date, datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from extensions import db


class UserRole(enum.Enum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    SCHEDULER = "scheduler"
    FIELD_SUPERVISOR = "field_supervisor"
    VIEWER = "viewer"


class ScheduleType(enum.Enum):
    GANTT = "gantt"
    LINEAR = "linear"
    PULL_PLANNING = "pull_planning"


class TaskStatus(enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class EquipmentType(enum.Enum):
    HEAVY_MACHINERY = "heavy_machinery"
    VEHICLES = "vehicles"
    TOOLS = "tools"
    GENERATORS = "generators"
    SAFETY_EQUIPMENT = "safety_equipment"
    SPECIALIZED = "specialized"


class EquipmentStatus(enum.Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"
    RESERVED = "reserved"


class MaintenanceType(enum.Enum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    EMERGENCY = "emergency"
    INSPECTION = "inspection"


class MaintenanceStatus(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    role = Column(db.Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    company_id = Column(Integer, ForeignKey("companies.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime)

    # Relationships
    company = relationship("Company", back_populates="users")
    projects = relationship("Project", back_populates="created_by_user")
    assigned_equipment = relationship("Equipment", back_populates="assigned_to_user")

    # Indexes are declared here rather than issued as DDL at start-up, so that
    # create_all() and Alembic both produce them on any backend.
    __table_args__ = (
        db.Index("ix_users_company", "company_id"),
        db.Index("ix_users_company_role", "company_id", "role"),
    )


class Company(db.Model):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    address = Column(Text)
    phone = Column(String(20))
    email = Column(String(120))
    azure_tenant_id = Column(String(100))
    fabric_workspace_id = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    users = relationship("User", back_populates="company")
    projects = relationship("Project", back_populates="company")
    powerbi_integrations = relationship("PowerBIIntegration", back_populates="company")
    equipment = relationship("Equipment", back_populates="company")
    suppliers = relationship("Supplier", back_populates="company")
    transactions = relationship("Transaction", back_populates="company")
    invoices = relationship("Invoice", back_populates="company")
    payments = relationship("Payment", back_populates="company")


# Equipment Management Models
class Equipment(db.Model):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True)
    equipment_number = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    equipment_type = Column(db.Enum(EquipmentType), nullable=False)
    manufacturer = Column(String(100))
    model = Column(String(100))
    serial_number = Column(String(100))
    year_manufactured = Column(Integer)
    purchase_date = Column(Date)
    purchase_cost = Column(Float)
    current_value = Column(Float)

    # Status and availability
    status = Column(db.Enum(EquipmentStatus), nullable=False, default=EquipmentStatus.AVAILABLE)
    location = Column(String(200))
    current_project_id = Column(Integer, ForeignKey("projects.id"))
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"))

    # Operational data
    operating_hours = Column(Float, default=0.0)
    fuel_capacity = Column(Float)
    max_load_capacity = Column(Float)
    specifications = Column(JSON)

    # Maintenance data
    last_maintenance_date = Column(Date)
    next_maintenance_date = Column(Date)
    maintenance_interval_hours = Column(Integer, default=250)
    warranty_expiry_date = Column(Date)

    # Insurance and compliance
    insurance_policy_number = Column(String(100))
    insurance_expiry_date = Column(Date)
    registration_number = Column(String(100))
    registration_expiry_date = Column(Date)

    # Ownership and company
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    is_owned = Column(Boolean, default=True)
    rental_rate_per_day = Column(Float)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))

    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, default=True)

    # Relationships
    company = relationship("Company", back_populates="equipment")
    current_project = relationship("Project", back_populates="assigned_equipment")
    assigned_to_user = relationship("User", back_populates="assigned_equipment")
    supplier = relationship("Supplier", back_populates="equipment")
    transactions = relationship("Transaction", back_populates="equipment")
    usage_logs = relationship(
        "EquipmentUsageLog", back_populates="equipment", cascade="all, delete-orphan"
    )
    maintenance_records = relationship(
        "MaintenanceRecord", back_populates="equipment", cascade="all, delete-orphan"
    )

    # Unique constraint per company
    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "equipment_number", name="uq_equipment_number_per_company"
        ),
        db.Index("ix_equipment_company_status", "company_id", "status"),
        db.Index("ix_equipment_company_type", "company_id", "equipment_type"),
        db.Index("ix_equipment_maintenance_due", "company_id", "next_maintenance_date"),
    )

    def utilization_rate(self, days: int = 30, as_of: date | None = None) -> float:
        """Percentage of available working hours this equipment was in use.

        Computed from recorded usage rather than returned as a constant. An
        eight-hour working day is assumed over the window; a machine logging
        four hours a day for a month reads as 50% utilised.

        Returns 0.0 when nothing has been logged, which is honest: no usage
        records means no measured utilisation, not average utilisation.
        """
        if days < 1:
            raise ValueError(f"Utilisation window must be at least one day, got {days}")

        # The window is `days` calendar days inclusive of both ends, so the
        # hours numerator and the working-day denominator cover exactly the
        # same span. Deriving window_start from `days` rather than `days - 1`
        # made the numerator one day wider than the denominator, which read
        # back as 52.4% for a machine working half days.
        window_end = as_of or date.today()
        window_start = window_end - timedelta(days=days - 1)

        hours = sum(
            log.hours_used or 0
            for log in self.usage_logs
            if log.usage_date and window_start <= log.usage_date <= window_end
        )

        # Working days in the window, five per week.
        working_days = sum(
            1 for offset in range(days) if (window_start + timedelta(days=offset)).weekday() < 5
        )
        available_hours = working_days * 8
        if available_hours <= 0:
            return 0.0
        return round(min(100.0, hours / available_hours * 100), 1)

    @property
    def utilization_rate_30d(self) -> float:
        """Convenience for templates, which cannot pass arguments."""
        return self.utilization_rate()

    @property
    def total_hours_logged(self) -> float:
        return sum(log.hours_used or 0 for log in self.usage_logs)

    @property
    def days_until_maintenance(self):
        """Calculate days until next scheduled maintenance"""
        if self.next_maintenance_date:
            delta = self.next_maintenance_date - date.today()
            return delta.days
        return None

    @property
    def is_maintenance_due(self):
        """Check if maintenance is due"""
        if self.next_maintenance_date:
            return self.next_maintenance_date <= date.today()
        return False


class EquipmentUsageLog(db.Model):
    """Hours a machine actually worked on a given day.

    Utilisation is measured from these rows. Before they existed
    ``Equipment.utilization_rate`` returned a hardcoded 75.5, so every
    utilisation figure on every dashboard was the same invented number.
    """

    __tablename__ = "equipment_usage_logs"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    usage_date = Column(Date, nullable=False)
    hours_used = Column(Float, nullable=False, default=0.0)

    # Where the hours went, so utilisation can be attributed.
    project_id = Column(Integer, ForeignKey("projects.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))
    operator_id = Column(Integer, ForeignKey("users.id"))

    fuel_used = Column(Float)
    location = Column(String(200))
    notes = Column(Text)

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    equipment = relationship("Equipment", back_populates="usage_logs")
    project = relationship("Project")
    task = relationship("Task")
    operator = relationship("User", foreign_keys=[operator_id])

    __table_args__ = (
        # One entry per machine per day; two rows for the same day would
        # double-count hours and inflate utilisation.
        db.UniqueConstraint("equipment_id", "usage_date", name="uq_equipment_usage_per_day"),
        db.Index("ix_equipment_usage_equipment_date", "equipment_id", "usage_date"),
        db.Index("ix_equipment_usage_company_date", "company_id", "usage_date"),
        db.Index("ix_equipment_usage_project", "project_id"),
    )


class MaintenanceRecord(db.Model):
    """A scheduled or completed maintenance job against one machine."""

    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)

    maintenance_type = Column(db.Enum(MaintenanceType), nullable=False)
    status = Column(db.Enum(MaintenanceStatus), nullable=False, default=MaintenanceStatus.SCHEDULED)

    scheduled_date = Column(Date, nullable=False)
    completed_date = Column(Date)

    description = Column(Text, nullable=False)
    work_performed = Column(Text)

    # Cost and downtime, which is what makes maintenance analysable.
    labour_cost = Column(db.Numeric(12, 2), default=0)
    parts_cost = Column(db.Numeric(12, 2), default=0)
    downtime_hours = Column(Float, default=0.0)

    # Reading at the time of service, for interval-based scheduling.
    operating_hours_at_service = Column(Float)

    technician_id = Column(Integer, ForeignKey("users.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    equipment = relationship("Equipment", back_populates="maintenance_records")
    technician = relationship("User", foreign_keys=[technician_id])
    supplier = relationship("Supplier")

    __table_args__ = (
        db.Index("ix_maintenance_equipment", "equipment_id"),
        db.Index("ix_maintenance_company_status", "company_id", "status"),
        db.Index("ix_maintenance_scheduled", "company_id", "scheduled_date"),
    )

    @property
    def total_cost(self):
        return (self.labour_cost or 0) + (self.parts_cost or 0)

    @property
    def is_overdue(self) -> bool:
        """Scheduled, past its date, and not yet done."""
        if self.status in (MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED):
            return False
        return bool(self.scheduled_date and self.scheduled_date < date.today())


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    contact_person = Column(String(100))
    email = Column(String(120))
    phone = Column(String(20))
    address = Column(Text)
    website = Column(String(200))

    # Service details
    services_provided = Column(JSON)
    equipment_types = Column(JSON)
    service_areas = Column(JSON)

    # Business information
    business_license = Column(String(100))
    insurance_details = Column(JSON)
    payment_terms = Column(String(100))

    # Performance metrics
    reliability_rating = Column(Float, default=5.0)
    cost_rating = Column(Float, default=5.0)
    service_rating = Column(Float, default=5.0)

    # Company association
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, default=True)

    # Relationships
    company = relationship("Company", back_populates="suppliers")
    equipment = relationship("Equipment", back_populates="supplier")


# Financial Management Models


class TransactionType(enum.Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class PaymentMethod(enum.Enum):
    CASH = "cash"
    CHECK = "check"
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    ACH = "ach"
    WIRE_TRANSFER = "wire_transfer"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class InvoiceStatus(enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class ExpenseCategory(enum.Enum):
    LABOR = "labor"
    MATERIALS = "materials"
    EQUIPMENT = "equipment"
    SUBCONTRACTOR = "subcontractor"
    PERMITS = "permits"
    UTILITIES = "utilities"
    INSURANCE = "insurance"
    FUEL = "fuel"
    MAINTENANCE = "maintenance"
    OVERHEAD = "overhead"
    OTHER = "other"


class BudgetCategory(enum.Enum):
    LABOR = "labor"
    MATERIALS = "materials"
    EQUIPMENT = "equipment"
    SUBCONTRACTORS = "subcontractors"
    PERMITS_FEES = "permits_fees"
    UTILITIES = "utilities"
    INSURANCE = "insurance"
    CONTINGENCY = "contingency"
    OVERHEAD = "overhead"
    PROFIT = "profit"


class Transaction(db.Model):
    """General ledger transactions for all financial activities"""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    transaction_number = Column(String(50), nullable=False)
    transaction_type = Column(db.Enum(TransactionType), nullable=False)

    # Amount and currency
    amount = Column(db.Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="USD")

    # Transaction details
    description = Column(Text, nullable=False)
    transaction_date = Column(Date, nullable=False)
    reference_number = Column(String(100))

    # Categorization
    expense_category = Column(db.Enum(ExpenseCategory))

    # Project association
    project_id = Column(Integer, ForeignKey("projects.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))

    # Equipment association (for equipment-related costs)
    equipment_id = Column(Integer, ForeignKey("equipment.id"))

    # Payment information
    payment_method = Column(db.Enum(PaymentMethod))
    payment_reference = Column(String(200))

    # Vendor/Customer information
    vendor_customer_name = Column(String(200))

    # Document attachments
    receipt_url = Column(String(500))
    invoice_url = Column(String(500))
    supporting_documents = Column(JSON)

    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    approval_notes = Column(Text)

    # Company and audit
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company = relationship("Company", back_populates="transactions")
    project = relationship("Project", back_populates="transactions")
    task = relationship("Task", back_populates="transactions")
    equipment = relationship("Equipment", back_populates="transactions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    # Indexes for performance
    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "transaction_number", name="uq_transaction_number_per_company"
        ),
        db.Index("ix_transactions_company_date", "company_id", "transaction_date"),
        db.Index("ix_transactions_project_date", "project_id", "transaction_date"),
        db.Index("ix_transactions_category", "company_id", "expense_category"),
    )


class ProjectBudget(db.Model):
    """Project budget tracking with categories"""

    __tablename__ = "project_budgets"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Budget details
    budget_category = Column(db.Enum(BudgetCategory), nullable=False)
    budgeted_amount = Column(db.Numeric(15, 2), nullable=False)
    revised_amount = Column(db.Numeric(15, 2))

    # Tracking
    committed_amount = Column(db.Numeric(15, 2), default=0)
    actual_amount = Column(db.Numeric(15, 2), default=0)

    # Metadata
    description = Column(Text)
    notes = Column(Text)

    # Versioning for budget revisions
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)

    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="budgets")
    created_by = relationship("User", foreign_keys=[created_by_id])

    # Constraints
    __table_args__ = (
        db.UniqueConstraint(
            "project_id", "budget_category", "version", name="uq_project_budget_category_version"
        ),
        db.Index("ix_project_budgets_current", "project_id", "is_current"),
    )


class Invoice(db.Model):
    """Invoice management for billing clients"""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), nullable=False)

    # Client information
    client_name = Column(String(200), nullable=False)
    client_email = Column(String(200))
    client_address = Column(Text)

    # Invoice details
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(db.Numeric(15, 2), nullable=False)
    tax_rate = Column(db.Numeric(5, 4), default=0)
    tax_amount = Column(db.Numeric(15, 2), default=0)
    discount_amount = Column(db.Numeric(15, 2), default=0)
    total_amount = Column(db.Numeric(15, 2), nullable=False)

    # Payment tracking
    paid_amount = Column(db.Numeric(15, 2), default=0)
    status = Column(db.Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)

    # Project association
    project_id = Column(Integer, ForeignKey("projects.id"))

    # Terms and notes
    payment_terms = Column(String(100))
    notes = Column(Text)
    internal_notes = Column(Text)

    # Document generation
    pdf_url = Column(String(500))
    sent_at = Column(DateTime)
    viewed_at = Column(DateTime)

    # Stripe integration
    stripe_invoice_id = Column(String(100))
    stripe_payment_intent_id = Column(String(100))

    # Company and audit
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company = relationship("Company", back_populates="invoices")
    project = relationship("Project", back_populates="invoices")
    created_by = relationship("User", foreign_keys=[created_by_id])
    invoice_items = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    payments = relationship("Payment", back_populates="invoice")

    # Constraints
    __table_args__ = (
        db.UniqueConstraint("company_id", "invoice_number", name="uq_invoice_number_per_company"),
        db.Index("ix_invoices_company_status", "company_id", "status"),
        db.Index("ix_invoices_due_date", "due_date"),
    )

    # ── Balance and status ────────────────────────────────────────────────
    # paid_amount is a stored column so that outstanding-balance queries stay
    # a single scan, but it is only ever written by recalculate_payments(),
    # which derives it from the payment rows. Nothing else should set it.

    @property
    def settled_payments(self):
        """Payments that actually cleared. Pending and failed do not count."""
        return [p for p in self.payments if p.status == PaymentStatus.COMPLETED]

    @property
    def amount_paid(self):
        return sum((p.amount or 0) for p in self.settled_payments)

    @property
    def balance_due(self):
        return (self.total_amount or 0) - self.amount_paid

    @property
    def is_settled(self) -> bool:
        return self.balance_due <= 0

    @property
    def days_overdue(self) -> int:
        """Days past the due date, or 0 if settled, unsent, or not yet due."""
        if self.status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
            return 0
        if self.is_settled or not self.due_date:
            return 0
        return max(0, (date.today() - self.due_date).days)

    def derive_status(self) -> "InvoiceStatus":
        """What the status should be, given the payments and the date.

        Draft and cancelled are set by a person and are never overridden — an
        invoice nobody has sent cannot become overdue.
        """
        if self.status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
            return self.status
        if self.is_settled:
            return InvoiceStatus.PAID
        if self.amount_paid > 0:
            return InvoiceStatus.PARTIAL
        if self.due_date and self.due_date < date.today():
            return InvoiceStatus.OVERDUE
        return self.status if self.status == InvoiceStatus.VIEWED else InvoiceStatus.SENT

    def recalculate_payments(self) -> None:
        """Recompute the cached total and status from the payment rows."""
        self.paid_amount = self.amount_paid
        self.status = self.derive_status()


class InvoiceItem(db.Model):
    """Individual line items for invoices"""

    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)

    # Item details
    description = Column(Text, nullable=False)
    quantity = Column(db.Numeric(10, 2), nullable=False, default=1)
    unit_price = Column(db.Numeric(15, 2), nullable=False)
    line_total = Column(db.Numeric(15, 2), nullable=False)

    # Optional categorization
    item_category = Column(String(100))

    # Task/project reference
    task_id = Column(Integer, ForeignKey("tasks.id"))

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    invoice = relationship("Invoice", back_populates="invoice_items")
    task = relationship("Task")


class Payment(db.Model):
    """Payment records for invoices and general payments"""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), nullable=False)

    # Payment details
    amount = Column(db.Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="USD")
    payment_date = Column(Date, nullable=False)
    payment_method = Column(db.Enum(PaymentMethod), nullable=False)

    # Status and processing
    status = Column(db.Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    reference_number = Column(String(200))

    # Invoice association (optional - for invoice payments)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))

    # Customer/payer information
    payer_name = Column(String(200))
    payer_email = Column(String(200))

    # Payment processor integration
    stripe_payment_id = Column(String(100))
    processor_fee = Column(db.Numeric(10, 2))
    net_amount = Column(db.Numeric(15, 2))

    # Notes and metadata
    description = Column(Text)
    internal_notes = Column(Text)
    failure_reason = Column(Text)

    # Company and audit
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    processed_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company = relationship("Company", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    processed_by = relationship("User", foreign_keys=[processed_by_id])

    # Constraints
    __table_args__ = (
        db.UniqueConstraint("company_id", "payment_number", name="uq_payment_number_per_company"),
        db.Index("ix_payments_company_status", "company_id", "status"),
        db.Index("ix_payments_date", "payment_date"),
    )


class Project(db.Model):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    # Unique per company, not globally: two tenants may each run a project
    # numbered "P-001", and a global constraint makes the second import fail.
    project_number = Column(String(50))
    company_id = Column(Integer, ForeignKey("companies.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget = Column(Float)
    location = Column(String(200))
    status = Column(String(20), default="active")
    schedule_type = Column(db.Enum(ScheduleType), default=ScheduleType.GANTT)
    # The "as of" date that progress is reported against. Every schedule metric
    # is measured relative to this: an activity is late only with respect to a
    # data date. Defaults to the project start until the first update.
    data_date = Column(Date)
    azure_project_id = Column(String(100))
    fabric_dataset_id = Column(String(100))
    # The construction template this project was created from, if any.
    # blueprints/project_templates.py assigned this on every template-created
    # project, but no column existed, so SQLAlchemy kept it as a transient
    # instance attribute and dropped it at commit -- the provenance was never
    # recorded -- while the "my templates" page raised AttributeError querying
    # it. Nullable: projects created directly have no template.
    template_used = Column(String(100), index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company = relationship("Company", back_populates="projects")
    created_by_user = relationship("User", back_populates="projects")
    assigned_equipment = relationship("Equipment", back_populates="current_project")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="project", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="project")
    budgets = relationship("ProjectBudget", back_populates="project", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="project")
    baselines = relationship(
        "ScheduleBaseline", back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def current_baseline(self):
        return next((b for b in self.baselines if b.is_current), None)

    @property
    def effective_data_date(self):
        """The reporting date, falling back to the project start."""
        return self.data_date or self.start_date

    __table_args__ = (
        db.UniqueConstraint("company_id", "project_number", name="uq_project_number_per_company"),
        db.Index("ix_projects_company", "company_id"),
        db.Index("ix_projects_company_status", "company_id", "status"),
        db.Index("ix_projects_created_by", "created_by"),
    )


class Task(db.Model):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"))
    wbs_code = Column(String(50))
    # Current plan. These are an output of the CPM calculation.
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    duration = Column(Integer, nullable=False)  # in days
    progress = Column(Float, default=0.0)  # percentage
    status = Column(db.Enum(TaskStatus), default=TaskStatus.NOT_STARTED)
    priority = Column(String(10), default="medium")

    # The approved baseline these dates are measured against, copied from the
    # current ScheduleBaseline. Without a baseline there is nothing to be late
    # relative to, so DCMA checks 11 and 14 cannot be evaluated at all.
    baseline_start = Column(Date)
    baseline_finish = Column(Date)
    baseline_duration = Column(Integer)

    # What actually happened. actual_finish being set is what makes an activity
    # complete; the status enum is a label, these are the record.
    actual_start = Column(Date)
    actual_finish = Column(Date)
    location = Column(String(200))  # for linear scheduling
    station_start = Column(Float)  # for linear scheduling
    station_end = Column(Float)  # for linear scheduling
    pull_plan_week = Column(Integer)  # for pull planning
    constraints = Column(JSON)
    azure_ai_recommendations = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    project = relationship("Project", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[id])
    subtasks = relationship("Task", overlaps="parent_task")
    # Both sides of the logic tie cascade. Without this, deleting a project
    # left TaskDependency rows behind with their foreign keys nulled out,
    # which violates the NOT NULL constraint and corrupts the logic network
    # for every remaining project in the table.
    dependencies = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.task_id",
        cascade="all, delete-orphan",
    )
    dependents = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.predecessor_task_id",
        cascade="all, delete-orphan",
    )
    resource_assignments = relationship(
        "ResourceAssignment", back_populates="task", cascade="all, delete-orphan"
    )
    transactions = relationship("Transaction", back_populates="task")

    __table_args__ = (
        db.Index("ix_tasks_project", "project_id"),
        db.Index("ix_tasks_project_status", "project_id", "status"),
        db.Index("ix_tasks_project_start", "project_id", "start_date"),
        db.Index("ix_tasks_project_actual_finish", "project_id", "actual_finish"),
        db.Index("ix_tasks_parent", "parent_task_id"),
    )

    @property
    def is_complete(self) -> bool:
        """Complete means a recorded actual finish, not a status label."""
        return self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        return self.actual_start is not None

    @property
    def start_variance_days(self):
        """Calendar days late starting. Negative means early. None if unknown."""
        if self.actual_start is None or self.baseline_start is None:
            return None
        return (self.actual_start - self.baseline_start).days

    @property
    def finish_variance_days(self):
        """Calendar days late finishing. Negative means early. None if unknown."""
        if self.actual_finish is None or self.baseline_finish is None:
            return None
        return (self.actual_finish - self.baseline_finish).days

    @property
    def plan_vs_baseline_days(self):
        """Slip in the *forecast* against baseline, for work not yet finished.

        This is the early-warning number: it moves before an activity is late,
        because it compares where the plan now says it will finish.
        """
        if self.end_date is None or self.baseline_finish is None:
            return None
        return (self.end_date - self.baseline_finish).days


class ScheduleBaseline(db.Model):
    """A frozen snapshot of a project's dates, to measure progress against.

    The current baseline is also denormalised onto ``Task.baseline_*`` so the
    common case — "is this activity late?" — is a column read rather than a
    join plus a JSON lookup. This table keeps the history, which is what makes
    revision-to-revision comparison possible later.
    """

    __tablename__ = "schedule_baselines"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(120), nullable=False)
    notes = Column(Text)

    # {task_id (as string): {"start": iso, "finish": iso, "duration": int}}
    snapshot = Column(JSON, nullable=False)

    # Exactly one baseline per project is current; setting a new one clears
    # the flag on the others.
    is_current = Column(Boolean, default=True, nullable=False)

    set_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    set_by_id = Column(Integer, ForeignKey("users.id"))

    project = relationship("Project", back_populates="baselines")
    set_by = relationship("User", foreign_keys=[set_by_id])

    __table_args__ = (
        db.Index("ix_schedule_baselines_project", "project_id"),
        db.Index("ix_schedule_baselines_current", "project_id", "is_current"),
    )

    @property
    def task_count(self) -> int:
        return len(self.snapshot or {})


class TaskDependency(db.Model):
    __tablename__ = "task_dependencies"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    predecessor_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    dependency_type = Column(String(10), default="FS")  # FS, SS, FF, SF
    lag_days = Column(Integer, default=0)

    __table_args__ = (
        db.Index("ix_task_dependencies_task_id", "task_id"),
        db.Index("ix_task_dependencies_predecessor_task_id", "predecessor_task_id"),
        # The same pair must not be linked twice; duplicate logic silently
        # doubles the constraint in the forward pass.
        db.UniqueConstraint("task_id", "predecessor_task_id", name="uq_task_dependency_pair"),
    )


class Resource(db.Model):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # labor, equipment, material
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    unit = Column(String(20))
    unit_cost = Column(Float)
    total_quantity = Column(Float)
    available_quantity = Column(Float)
    location = Column(String(200))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    project = relationship("Project", back_populates="resources")
    assignments = relationship(
        "ResourceAssignment", back_populates="resource", cascade="all, delete-orphan"
    )

    __table_args__ = (db.Index("ix_resources_project", "project_id"),)


class ResourceAssignment(db.Model):
    __tablename__ = "resource_assignments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    assignment_date = Column(Date)

    # Relationships
    task = relationship("Task", back_populates="resource_assignments")
    resource = relationship("Resource", back_populates="assignments")

    __table_args__ = (
        db.Index("ix_resource_assignments_task_id", "task_id"),
        db.Index("ix_resource_assignments_resource_id", "resource_id"),
    )


class AzureIntegration(db.Model):
    __tablename__ = "azure_integrations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    service_type = Column(String(50), nullable=False)  # ai, fabric, foundry
    endpoint_url = Column(String(500))
    api_key_encrypted = Column(String(500))
    workspace_id = Column(String(100))
    last_sync = Column(DateTime)
    sync_status = Column(String(20), default="pending")
    configuration = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.Index("ix_azure_integrations_project", "project_id"),)


class ScheduleOptimization(db.Model):
    __tablename__ = "schedule_optimizations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    optimization_type = Column(String(50))  # time, cost, resource
    parameters = Column(JSON)
    results = Column(JSON)
    recommended_changes = Column(JSON)
    confidence_score = Column(Float)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    applied_at = Column(DateTime)


class PowerBIIntegration(db.Model):
    __tablename__ = "powerbi_integrations"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    workspace_id = Column(String(100), nullable=False)
    sync_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sync_status = Column(String(20), default="pending")  # pending, completed, failed
    records_synced = Column(Integer, default=0)
    error_message = Column(Text)

    # Relationships
    company = relationship("Company", back_populates="powerbi_integrations")

    __table_args__ = (db.Index("ix_powerbi_integrations_company", "company_id"),)


class AuditLog(db.Model):
    """Audit log model for tracking user actions"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))  # project, task, user, etc.
    resource_id = Column(Integer)
    details = Column(Text)  # JSON string with additional details
    ip_address = Column(String(45))
    user_agent = Column(Text)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User")
    company = relationship("Company")

    __table_args__ = (
        db.Index("ix_audit_logs_company_timestamp", "company_id", "timestamp"),
        db.Index("ix_audit_logs_user_id", "user_id"),
        db.Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} by user {self.user_id}>"
