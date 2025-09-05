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
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="project", cascade="all, delete-orphan")

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
    subtasks = relationship("Task")
    dependencies = relationship("TaskDependency", foreign_keys="TaskDependency.task_id")
    resource_assignments = relationship("ResourceAssignment", back_populates="task")

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
