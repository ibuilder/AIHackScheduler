from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import Project, Task, Company, TaskStatus, UserRole
from extensions import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Get user's projects
    if current_user.role == UserRole.ADMIN:
        projects = Project.query.filter_by(company_id=current_user.company_id).limit(5).all()
    else:
        projects = Project.query.filter_by(
            company_id=current_user.company_id,
            created_by=current_user.id
        ).limit(5).all()
    
    # Get recent tasks
    recent_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).order_by(Task.updated_at.desc()).limit(10).all()
    
    # Calculate dashboard statistics
    total_projects = Project.query.filter_by(company_id=current_user.company_id).count()
    active_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id,
        Task.status.in_([TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS])
    ).count()
    
    return render_template('reports/dashboard.html',
                         projects=projects,
                         recent_tasks=recent_tasks,
                         total_projects=total_projects,
                         active_tasks=active_tasks)

@main_bp.route('/health')
def health_check():
    return {'status': 'healthy', 'service': 'BBSchedule Platform'}, 200
