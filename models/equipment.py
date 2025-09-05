"""
Equipment Management Models for BBSchedule Platform
Comprehensive equipment tracking, maintenance, and utilization management
"""

from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float, Date, JSON, Enum
from sqlalchemy.orm import relationship
from extensions import db
import enum

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

class Equipment(db.Model):
    __tablename__ = 'equipment'
    
    id = Column(Integer, primary_key=True)
    equipment_number = Column(String(50), unique=True, nullable=False)
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
    specifications = Column(JSON)  # Store technical specifications as JSON
    
    # Maintenance data
    last_maintenance_date = Column(Date)
    next_maintenance_date = Column(Date)
    maintenance_interval_hours = Column(Integer, default=250)  # Hours between maintenance
    warranty_expiry_date = Column(Date)
    
    # Insurance and compliance
    insurance_policy_number = Column(String(100))
    insurance_expiry_date = Column(Date)
    registration_number = Column(String(100))
    registration_expiry_date = Column(Date)
    
    # Ownership and company
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    is_owned = Column(Boolean, default=True)  # True if owned, False if rented
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
    maintenance_records = relationship("MaintenanceRecord", back_populates="equipment", cascade="all, delete-orphan")
    usage_logs = relationship("EquipmentUsageLog", back_populates="equipment", cascade="all, delete-orphan")
    inspections = relationship("EquipmentInspection", back_populates="equipment", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Equipment {self.equipment_number}: {self.name}>'
    
    @property
    def utilization_rate(self):
        """Calculate equipment utilization rate over last 30 days"""
        # This would calculate based on usage logs
        # Simplified calculation for now
        return 75.5  # Placeholder
    
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
    
    @property
    def total_operating_cost(self):
        """Calculate total operating cost including maintenance"""
        # This would include fuel, maintenance, depreciation, etc.
        # Simplified calculation
        maintenance_cost = sum(record.cost for record in self.maintenance_records if record.cost)
        return maintenance_cost + (self.operating_hours * 25.0)  # $25/hour operating cost

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
    services_provided = Column(JSON)  # List of services: rental, sales, maintenance, etc.
    equipment_types = Column(JSON)  # Types of equipment they provide
    service_areas = Column(JSON)  # Geographic areas they serve
    
    # Business information
    business_license = Column(String(100))
    insurance_details = Column(JSON)
    payment_terms = Column(String(100))
    
    # Performance metrics
    reliability_rating = Column(Float, default=5.0)  # 1-5 scale
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
    maintenance_records = relationship("MaintenanceRecord", back_populates="performed_by_supplier")

class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey('equipment.id'), nullable=False)
    maintenance_type = Column(db.Enum(MaintenanceType), nullable=False)
    status = Column(db.Enum(MaintenanceStatus), nullable=False, default=MaintenanceStatus.SCHEDULED)
    
    # Scheduling information
    scheduled_date = Column(Date, nullable=False)
    completed_date = Column(Date)
    estimated_duration_hours = Column(Float)
    actual_duration_hours = Column(Float)
    
    # Work details
    description = Column(Text, nullable=False)
    work_performed = Column(Text)
    parts_used = Column(JSON)  # List of parts and quantities
    technician_notes = Column(Text)
    
    # Personnel
    assigned_technician_id = Column(Integer, ForeignKey('users.id'))
    performed_by_supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    
    # Cost tracking
    labor_cost = Column(Float, default=0.0)
    parts_cost = Column(Float, default=0.0)
    other_costs = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    
    # Documentation
    before_photos = Column(JSON)  # URLs to before photos
    after_photos = Column(JSON)   # URLs to after photos
    documents = Column(JSON)      # URLs to related documents
    
    # Impact on equipment
    operating_hours_at_maintenance = Column(Float)
    next_maintenance_hours = Column(Float)
    next_maintenance_date = Column(Date)
    
    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Relationships
    equipment = relationship("Equipment", back_populates="maintenance_records")
    assigned_technician = relationship("User", foreign_keys=[assigned_technician_id])
    performed_by_supplier = relationship("Supplier", back_populates="maintenance_records")
    created_by = relationship("User", foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f'<MaintenanceRecord {self.id}: {self.equipment.name} - {self.maintenance_type.value}>'
    
    @property
    def cost(self):
        """Get total maintenance cost"""
        return self.total_cost or (self.labor_cost + self.parts_cost + self.other_costs)
    
    @property
    def is_overdue(self):
        """Check if maintenance is overdue"""
        if self.status == MaintenanceStatus.SCHEDULED:
            return self.scheduled_date < date.today()
        return False

class EquipmentUsageLog(db.Model):
    __tablename__ = 'equipment_usage_logs'
    
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey('equipment.id'), nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    
    # Usage tracking
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    operator_id = Column(Integer, ForeignKey('users.id'))
    
    # Operational data
    start_operating_hours = Column(Float)
    end_operating_hours = Column(Float)
    fuel_consumed = Column(Float)
    location_start = Column(String(200))
    location_end = Column(String(200))
    
    # Usage details
    work_description = Column(Text)
    productivity_notes = Column(Text)
    issues_encountered = Column(Text)
    
    # Performance metrics
    efficiency_rating = Column(Float)  # 1-5 scale
    fuel_efficiency = Column(Float)    # Miles/gallon or hours/gallon
    
    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    logged_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Relationships
    equipment = relationship("Equipment", back_populates="usage_logs")
    project = relationship("Project")
    task = relationship("Task")
    operator = relationship("User", foreign_keys=[operator_id])
    logged_by = relationship("User", foreign_keys=[logged_by_id])
    
    @property
    def hours_used(self):
        """Calculate hours used in this session"""
        if self.end_operating_hours and self.start_operating_hours:
            return self.end_operating_hours - self.start_operating_hours
        return 0.0
    
    @property
    def session_duration(self):
        """Calculate total session duration"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

class EquipmentInspection(db.Model):
    __tablename__ = 'equipment_inspections'
    
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey('equipment.id'), nullable=False)
    
    # Inspection details
    inspection_date = Column(Date, nullable=False)
    inspection_type = Column(String(50))  # Daily, Weekly, Monthly, Annual, etc.
    inspector_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Checklist and results
    checklist_items = Column(JSON)  # Standardized inspection checklist
    passed_items = Column(JSON)     # Items that passed inspection
    failed_items = Column(JSON)     # Items that failed inspection
    
    # Overall assessment
    overall_condition = Column(String(20))  # Excellent, Good, Fair, Poor
    safety_compliant = Column(Boolean, default=True)
    operational_status = Column(String(20))  # Operational, Needs Repair, Out of Service
    
    # Issues and recommendations
    issues_found = Column(Text)
    recommendations = Column(Text)
    required_actions = Column(JSON)  # List of required actions with priorities
    
    # Follow-up
    next_inspection_date = Column(Date)
    follow_up_required = Column(Boolean, default=False)
    follow_up_notes = Column(Text)
    
    # Documentation
    photos = Column(JSON)      # URLs to inspection photos
    documents = Column(JSON)   # URLs to related documents
    signature = Column(String(500))  # Digital signature of inspector
    
    # Audit fields
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    equipment = relationship("Equipment", back_populates="inspections")
    inspector = relationship("User")
    
    @property
    def inspection_score(self):
        """Calculate inspection score based on passed/failed items"""
        if not self.checklist_items:
            return 100.0
        
        total_items = len(self.checklist_items)
        passed_items = len(self.passed_items) if self.passed_items else 0
        
        return (passed_items / total_items) * 100 if total_items > 0 else 100.0