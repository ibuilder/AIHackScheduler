from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func
from models import Project, Task, Resource, ResourceAssignment, User, TaskStatus
from extensions import db

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/dashboard')
@login_required
def dashboard():
    # Get company projects
    projects = Project.query.filter_by(company_id=current_user.company_id).all()
    
    # Calculate key metrics
    total_projects = len(projects)
    active_projects = len([p for p in projects if p.status == 'active'])
    
    # Get task statistics
    total_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).count()
    
    completed_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id,
        Task.status == TaskStatus.COMPLETED
    ).count()
    
    overdue_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id,
        Task.end_date < datetime.now().date(),
        Task.status.in_([TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS])
    ).count()
    
    # Get project progress data for charts
    project_progress = []
    for project in projects[:10]:  # Top 10 projects
        tasks = Task.query.filter_by(project_id=project.id).all()
        if tasks:
            progress = sum(task.progress for task in tasks) / len(tasks)
            project_progress.append({
                'name': project.name,
                'progress': round(progress, 2)
            })
    
    # Get task status distribution
    status_counts = db.session.query(
        Task.status,
        func.count(Task.id).label('count')
    ).join(Project).filter(
        Project.company_id == current_user.company_id
    ).group_by(Task.status).all()
    
    status_distribution = [
        {'status': status.name, 'count': count} 
        for status, count in status_counts
    ]
    
    # Get recent activities
    recent_tasks = Task.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).order_by(Task.updated_at.desc()).limit(10).all()
    
    return render_template('reports/dashboard.html',
                         total_projects=total_projects,
                         active_projects=active_projects,
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         project_progress=project_progress,
                         status_distribution=status_distribution,
                         recent_tasks=recent_tasks)

@reports_bp.route('/project/<int:project_id>')
@login_required
def project_report(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get project tasks with statistics
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    # Calculate project metrics
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
    in_progress_tasks = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
    overdue_tasks = len([t for t in tasks if t.end_date < datetime.now().date() 
                        and t.status in [TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS]])
    
    # Calculate overall project progress
    overall_progress = (sum(task.progress for task in tasks) / total_tasks) if total_tasks > 0 else 0
    
    # Get resource utilization
    resources = Resource.query.filter_by(project_id=project_id).all()
    resource_utilization = []
    
    for resource in resources:
        assignments = ResourceAssignment.query.filter_by(resource_id=resource.id).all()
        total_assigned = sum(assignment.quantity for assignment in assignments)
        utilization = (total_assigned / resource.total_quantity * 100) if resource.total_quantity > 0 else 0
        
        resource_utilization.append({
            'name': resource.name,
            'type': resource.type,
            'utilization': round(utilization, 2),
            'total_quantity': resource.total_quantity,
            'assigned_quantity': total_assigned
        })
    
    # Get schedule performance
    on_time_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED 
                        and t.updated_at.date() <= t.end_date])
    late_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED 
                     and t.updated_at.date() > t.end_date])
    
    return render_template('reports/project_report.html',
                         project=project,
                         tasks=tasks,
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         in_progress_tasks=in_progress_tasks,
                         overdue_tasks=overdue_tasks,
                         overall_progress=round(overall_progress, 2),
                         resource_utilization=resource_utilization,
                         on_time_tasks=on_time_tasks,
                         late_tasks=late_tasks)

@reports_bp.route('/api/export/<int:project_id>')
@login_required
def export_report(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    export_format = request.args.get('format', 'json')
    
    # Get project data
    tasks = Task.query.filter_by(project_id=project_id).all()
    resources = Resource.query.filter_by(project_id=project_id).all()
    
    report_data = {
        'project': {
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'start_date': project.start_date.isoformat(),
            'end_date': project.end_date.isoformat(),
            'status': project.status,
            'location': project.location
        },
        'tasks': [
            {
                'id': task.id,
                'name': task.name,
                'start_date': task.start_date.isoformat(),
                'end_date': task.end_date.isoformat(),
                'duration': task.duration,
                'progress': task.progress,
                'status': task.status.name,
                'location': task.location
            }
            for task in tasks
        ],
        'resources': [
            {
                'id': resource.id,
                'name': resource.name,
                'type': resource.type,
                'unit': resource.unit,
                'unit_cost': resource.unit_cost,
                'total_quantity': resource.total_quantity
            }
            for resource in resources
        ]
    }
    
    if export_format == 'json':
        return jsonify(report_data)
    else:
        return jsonify({'error': 'Unsupported export format'}), 400
