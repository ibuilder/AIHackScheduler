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
    active_projects = Project.query.filter_by(company_id=current_user.company_id, status='active').count()
    
    total_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).count()
    
    active_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id,
        Task.status.in_([TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS])
    ).count()
    
    completed_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id,
        Task.status == TaskStatus.COMPLETED
    ).count()
    
    # Calculate real dashboard data
    try:
        # Project progress data for charts
        project_progress = []
        for project in projects[:5]:  # Top 5 projects
            if hasattr(project, 'tasks'):
                total_tasks = len(project.tasks)
                completed_tasks = len([t for t in project.tasks if t.status == TaskStatus.COMPLETED])
                progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                project_progress.append({
                    'name': project.name,
                    'progress': round(progress, 1),
                    'total_tasks': total_tasks,
                    'completed_tasks': completed_tasks
                })
        
        # Status distribution
        status_counts = {}
        all_tasks = Task.query.join(Project).filter(Project.company_id == current_user.company_id).all()
        for task in all_tasks:
            status = task.status.name
            status_counts[status] = status_counts.get(status, 0) + 1
        
        status_distribution = [{'status': k, 'count': v} for k, v in status_counts.items()]
        
        # Calculate overdue tasks (basic implementation)
        from datetime import date
        overdue_tasks = Task.query.join(Project).filter(
            Project.company_id == current_user.company_id,
            Task.end_date < date.today(),
            Task.status != TaskStatus.COMPLETED
        ).count()
        
    except Exception as e:
        app.logger.error(f"Dashboard data calculation error: {str(e)}")
        project_progress = []
        status_distribution = []
        overdue_tasks = 0
    
    return render_template('reports/dashboard.html',
                         projects=projects,
                         recent_tasks=recent_tasks,
                         total_projects=total_projects,
                         active_projects=active_projects,
                         total_tasks=total_tasks,
                         active_tasks=active_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         project_progress=project_progress,
                         status_distribution=status_distribution)

@main_bp.route('/health')
def health_check():
    return {'status': 'healthy', 'service': 'BBSchedule Platform'}, 200
