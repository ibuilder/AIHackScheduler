from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float, Date, JSON
from sqlalchemy.orm import relationship
from extensions import db
import enum

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
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    role = Column(db.Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    company_id = Column(Integer, ForeignKey('companies.id'))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime)
    
    # Relationships
    company = relationship("Company", back_populates="users")
    projects = relationship("Project", back_populates="created_by_user")
    assigned_equipment = relationship("Equipment", back_populates="assigned_to_user")

class Company(db.Model):
    __tablename__ = 'companies'
    
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
    __tablename__ = 'equipment'
    
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
    current_project_id = Column(Integer, ForeignKey('projects.id'))
    assigned_to_user_id = Column(Integer, ForeignKey('users.id'))
    
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
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    is_owned = Column(Boolean, default=True)
    rental_rate_per_day = Column(Float)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    
    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    
    # Relationships
    company = relationship("Company", back_populates="equipment")
    current_project = relationship("Project", back_populates="assigned_equipment")
    assigned_to_user = relationship("User", back_populates="assigned_equipment")
    supplier = relationship("Supplier", back_populates="equipment")
    transactions = relationship("Transaction", back_populates="equipment")
    
    # Unique constraint per company
    __table_args__ = (
        db.UniqueConstraint('company_id', 'equipment_number', name='uq_equipment_number_per_company'),
        db.Index('ix_equipment_company_status', 'company_id', 'status'),
        db.Index('ix_equipment_company_type', 'company_id', 'equipment_type'),
        db.Index('ix_equipment_maintenance_due', 'company_id', 'next_maintenance_date'),
    )
    
    @property
    def utilization_rate(self):
        """Calculate equipment utilization rate over last 30 days"""
        return 75.5  # Placeholder - would calculate from usage logs
    
    @property
    def days_until_maintenance(self):
        """Calculate days until next scheduled maintenance"""
        if self.next_maintenance_date:
            from datetime import date
            delta = self.next_maintenance_date - date.today()
            return delta.days
        return None
    
    @property
    def is_maintenance_due(self):
        """Check if maintenance is due"""
        if self.next_maintenance_date:
            from datetime import date
            return self.next_maintenance_date <= date.today()
        return False

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
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
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    
    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    
    # Relationships
    company = relationship("Company", back_populates="suppliers")
    equipment = relationship("Equipment", back_populates="supplier")

# Financial Management Models
from decimal import Decimal

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
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    transaction_number = Column(String(50), nullable=False)
    transaction_type = Column(db.Enum(TransactionType), nullable=False)
    
    # Amount and currency
    amount = Column(db.Numeric(15, 2), nullable=False)
    currency = Column(String(3), default='USD')
    
    # Transaction details
    description = Column(Text, nullable=False)
    transaction_date = Column(Date, nullable=False)
    reference_number = Column(String(100))
    
    # Categorization
    expense_category = Column(db.Enum(ExpenseCategory))
    
    # Project association
    project_id = Column(Integer, ForeignKey('projects.id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    
    # Equipment association (for equipment-related costs)
    equipment_id = Column(Integer, ForeignKey('equipment.id'))
    
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
    approved_by_id = Column(Integer, ForeignKey('users.id'))
    approved_at = Column(DateTime)
    approval_notes = Column(Text)
    
    # Company and audit
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    company = relationship("Company", back_populates="transactions")
    project = relationship("Project", back_populates="transactions")
    task = relationship("Task", back_populates="transactions")
    equipment = relationship("Equipment", back_populates="transactions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    
    # Indexes for performance
    __table_args__ = (
        db.UniqueConstraint('company_id', 'transaction_number', name='uq_transaction_number_per_company'),
        db.Index('ix_transactions_company_date', 'company_id', 'transaction_date'),
        db.Index('ix_transactions_project_date', 'project_id', 'transaction_date'),
        db.Index('ix_transactions_category', 'company_id', 'expense_category'),
    )

class ProjectBudget(db.Model):
    """Project budget tracking with categories"""
    __tablename__ = 'project_budgets'
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    
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
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Relationships
    project = relationship("Project", back_populates="budgets")
    created_by = relationship("User", foreign_keys=[created_by_id])
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('project_id', 'budget_category', 'version', name='uq_project_budget_category_version'),
        db.Index('ix_project_budgets_current', 'project_id', 'is_current'),
    )

class Invoice(db.Model):
    """Invoice management for billing clients"""
    __tablename__ = 'invoices'
    
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
    project_id = Column(Integer, ForeignKey('projects.id'))
    
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
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    company = relationship("Company", back_populates="invoices")
    project = relationship("Project", back_populates="invoices")
    created_by = relationship("User", foreign_keys=[created_by_id])
    invoice_items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('company_id', 'invoice_number', name='uq_invoice_number_per_company'),
        db.Index('ix_invoices_company_status', 'company_id', 'status'),
        db.Index('ix_invoices_due_date', 'due_date'),
    )

class InvoiceItem(db.Model):
    """Individual line items for invoices"""
    __tablename__ = 'invoice_items'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    
    # Item details
    description = Column(Text, nullable=False)
    quantity = Column(db.Numeric(10, 2), nullable=False, default=1)
    unit_price = Column(db.Numeric(15, 2), nullable=False)
    line_total = Column(db.Numeric(15, 2), nullable=False)
    
    # Optional categorization
    item_category = Column(String(100))
    
    # Task/project reference
    task_id = Column(Integer, ForeignKey('tasks.id'))
    
    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    invoice = relationship("Invoice", back_populates="invoice_items")
    task = relationship("Task")

class Payment(db.Model):
    """Payment records for invoices and general payments"""
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), nullable=False)
    
    # Payment details
    amount = Column(db.Numeric(15, 2), nullable=False)
    currency = Column(String(3), default='USD')
    payment_date = Column(Date, nullable=False)
    payment_method = Column(db.Enum(PaymentMethod), nullable=False)
    
    # Status and processing
    status = Column(db.Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    reference_number = Column(String(200))
    
    # Invoice association (optional - for invoice payments)
    invoice_id = Column(Integer, ForeignKey('invoices.id'))
    
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
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    processed_by_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    company = relationship("Company", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    processed_by = relationship("User", foreign_keys=[processed_by_id])
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('company_id', 'payment_number', name='uq_payment_number_per_company'),
        db.Index('ix_payments_company_status', 'company_id', 'status'),
        db.Index('ix_payments_date', 'payment_date'),
    )

class Project(db.Model):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    project_number = Column(String(50), unique=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    created_by = Column(Integer, ForeignKey('users.id'))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget = Column(Float)
    location = Column(String(200))
    status = Column(String(20), default='active')
    schedule_type = Column(db.Enum(ScheduleType), default=ScheduleType.GANTT)
    azure_project_id = Column(String(100))
    fabric_dataset_id = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    company = relationship("Company", back_populates="projects")
    created_by_user = relationship("User", back_populates="projects")
    assigned_equipment = relationship("Equipment", back_populates="current_project")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="project", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="project")
    budgets = relationship("ProjectBudget", back_populates="project", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="project")

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    parent_task_id = Column(Integer, ForeignKey('tasks.id'))
    wbs_code = Column(String(50))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    duration = Column(Integer, nullable=False)  # in days
    progress = Column(Float, default=0.0)  # percentage
    status = Column(db.Enum(TaskStatus), default=TaskStatus.NOT_STARTED)
    priority = Column(String(10), default='medium')
    location = Column(String(200))  # for linear scheduling
    station_start = Column(Float)  # for linear scheduling
    station_end = Column(Float)  # for linear scheduling
    pull_plan_week = Column(Integer)  # for pull planning
    constraints = Column(JSON)
    azure_ai_recommendations = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    project = relationship("Project", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[id])
    subtasks = relationship("Task", overlaps="parent_task")
    dependencies = relationship("TaskDependency", foreign_keys="TaskDependency.task_id")
    resource_assignments = relationship("ResourceAssignment", back_populates="task")
    transactions = relationship("Transaction", back_populates="task")

class TaskDependency(db.Model):
    __tablename__ = 'task_dependencies'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    predecessor_task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    dependency_type = Column(String(10), default='FS')  # FS, SS, FF, SF
    lag_days = Column(Integer, default=0)

class Resource(db.Model):
    __tablename__ = 'resources'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # labor, equipment, material
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    unit = Column(String(20))
    unit_cost = Column(Float)
    total_quantity = Column(Float)
    available_quantity = Column(Float)
    location = Column(String(200))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    project = relationship("Project", back_populates="resources")
    assignments = relationship("ResourceAssignment", back_populates="resource")

class ResourceAssignment(db.Model):
    __tablename__ = 'resource_assignments'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    resource_id = Column(Integer, ForeignKey('resources.id'), nullable=False)
    quantity = Column(Float, nullable=False)
    assignment_date = Column(Date)
    
    # Relationships
    task = relationship("Task", back_populates="resource_assignments")
    resource = relationship("Resource", back_populates="assignments")

class AzureIntegration(db.Model):
    __tablename__ = 'azure_integrations'
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    service_type = Column(String(50), nullable=False)  # ai, fabric, foundry
    endpoint_url = Column(String(500))
    api_key_encrypted = Column(String(500))
    workspace_id = Column(String(100))
    last_sync = Column(DateTime)
    sync_status = Column(String(20), default='pending')
    configuration = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ScheduleOptimization(db.Model):
    __tablename__ = 'schedule_optimizations'
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    optimization_type = Column(String(50))  # time, cost, resource
    parameters = Column(JSON)
    results = Column(JSON)
    recommended_changes = Column(JSON)
    confidence_score = Column(Float)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    applied_at = Column(DateTime)

class PowerBIIntegration(db.Model):
    __tablename__ = 'powerbi_integrations'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    workspace_id = Column(String(100), nullable=False)
    sync_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sync_status = Column(String(20), default='pending')  # pending, completed, failed
    records_synced = Column(Integer, default=0)
    error_message = Column(Text)
    
    # Relationships
    company = relationship("Company", back_populates="powerbi_integrations")

class AuditLog(db.Model):
    """Audit log model for tracking user actions"""
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    company_id = Column(Integer, ForeignKey('companies.id'))
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
    
    def __repr__(self):
        return f'<AuditLog {self.action} by user {self.user_id}>'
