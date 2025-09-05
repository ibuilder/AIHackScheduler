from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import Project, Task, TaskDependency, ResourceAssignment
from extensions import db
from services.schedule_optimizer import ScheduleOptimizer

scheduling_bp = Blueprint('scheduling', __name__)

@scheduling_bp.route('/gantt/<int:project_id>')
@login_required
def gantt_view(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return redirect(url_for('projects.list_projects'))
    
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.start_date).all()
    
    # Format tasks for Gantt chart
    gantt_tasks = []
    for task in tasks:
        gantt_tasks.append({
            'id': task.id,
            'name': task.name,
            'start': task.start_date.isoformat(),
            'end': task.end_date.isoformat(),
            'progress': task.progress,
            'status': task.status.name,
            'parent': task.parent_task_id,
            'dependencies': [dep.predecessor_task_id for dep in task.dependencies]
        })
    
    return render_template('scheduling/gantt.html', 
                         project=project, 
                         tasks=gantt_tasks)

@scheduling_bp.route('/linear/<int:project_id>')
@login_required
def linear_view(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return redirect(url_for('projects.list_projects'))
    
    # Get tasks with location data for linear scheduling
    tasks = Task.query.filter_by(project_id=project_id).filter(
        Task.station_start.isnot(None),
        Task.station_end.isnot(None)
    ).order_by(Task.start_date).all()
    
    linear_tasks = []
    for task in tasks:
        linear_tasks.append({
            'id': task.id,
            'name': task.name,
            'start_date': task.start_date.isoformat(),
            'end_date': task.end_date.isoformat(),
            'station_start': task.station_start,
            'station_end': task.station_end,
            'location': task.location,
            'progress': task.progress,
            'status': task.status.name
        })
    
    return render_template('scheduling/linear.html',
                         project=project,
                         tasks=linear_tasks)

@scheduling_bp.route('/pull-planning/<int:project_id>')
@login_required
def pull_planning_view(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return redirect(url_for('projects.list_projects'))
    
    # Get tasks organized by pull planning weeks
    tasks = Task.query.filter_by(project_id=project_id).filter(
        Task.pull_plan_week.isnot(None)
    ).order_by(Task.pull_plan_week, Task.start_date).all()
    
    # Organize tasks by week
    pull_plan_weeks = {}
    for task in tasks:
        week = task.pull_plan_week
        if week not in pull_plan_weeks:
            pull_plan_weeks[week] = []
        
        pull_plan_weeks[week].append({
            'id': task.id,
            'name': task.name,
            'start_date': task.start_date.isoformat(),
            'end_date': task.end_date.isoformat(),
            'duration': task.duration,
            'status': task.status.name,
            'progress': task.progress,
            'constraints': task.constraints or []
        })
    
    return render_template('scheduling/pull_planning.html',
                         project=project,
                         pull_plan_weeks=pull_plan_weeks)

@scheduling_bp.route('/api/tasks/<int:task_id>/update', methods=['PUT'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Check permissions
    if current_user.company_id != task.project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    
    # Update task fields
    if 'name' in data:
        task.name = data['name']
    if 'start_date' in data:
        task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    if 'end_date' in data:
        task.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    if 'duration' in data:
        task.duration = data['duration']
    if 'progress' in data:
        task.progress = data['progress']
    if 'status' in data:
        task.status = data['status']
    if 'station_start' in data:
        task.station_start = data['station_start']
    if 'station_end' in data:
        task.station_end = data['station_end']
    if 'pull_plan_week' in data:
        task.pull_plan_week = data['pull_plan_week']
    
    task.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'id': task.id,
        'name': task.name,
        'start_date': task.start_date.isoformat(),
        'end_date': task.end_date.isoformat(),
        'status': task.status.name,
        'progress': task.progress
    })

@scheduling_bp.route('/api/optimize/<int:project_id>', methods=['POST'])
@login_required
def optimize_schedule(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    optimizer = ScheduleOptimizer()
    optimization_type = request.json.get('type', 'time')
    
    try:
        results = optimizer.optimize_project_schedule(project_id, optimization_type)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
