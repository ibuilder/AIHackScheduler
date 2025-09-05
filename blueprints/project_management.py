from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date
from models import Project, Task, Company, UserRole, TaskStatus, ScheduleType
from extensions import db
import logging

project_mgmt_bp = Blueprint('project_mgmt', __name__)

@project_mgmt_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_project():
    """Create a new project"""
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            description = request.form.get('description')
            project_number = request.form.get('project_number')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            budget = request.form.get('budget')
            location = request.form.get('location')
            schedule_type = request.form.get('schedule_type', 'GANTT')
            
            # Validation
            if not all([name, start_date, end_date]):
                flash('Name, start date, and end date are required', 'error')
                return render_template('projects/create.html')
            
            # Parse dates
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if end_date <= start_date:
                flash('End date must be after start date', 'error')
                return render_template('projects/create.html')
            
            # Create project
            project = Project()
            project.name = name
            project.description = description
            project.project_number = project_number
            project.company_id = current_user.company_id
            project.created_by = current_user.id
            project.start_date = start_date
            project.end_date = end_date
            project.budget = float(budget) if budget else None
            project.location = location
            project.schedule_type = ScheduleType[schedule_type]
            
            db.session.add(project)
            db.session.commit()
            
            logging.info(f"New project created: {project.name} by user {current_user.id}")
            flash('Project created successfully!', 'success')
            return redirect(url_for('projects.project_detail', project_id=project.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Project creation error: {str(e)}")
            flash('Error creating project. Please try again.', 'error')
    
    return render_template('projects/create.html')

@project_mgmt_bp.route('/quick-task', methods=['POST'])
@login_required
def quick_add_task():
    """Quick add task via AJAX"""
    try:
        project_id = request.json.get('project_id')
        task_name = request.json.get('name')
        duration = request.json.get('duration', 1)
        
        if not all([project_id, task_name]):
            return jsonify({'error': 'Project ID and task name required'}), 400
        
        # Verify project access
        project = Project.query.get_or_404(project_id)
        if project.company_id != current_user.company_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Create task
        task = Task()
        task.name = task_name
        task.project_id = project_id
        task.duration = int(duration)
        task.start_date = date.today()
        task.end_date = date.today()  # Will be calculated properly later
        task.status = TaskStatus.NOT_STARTED
        
        db.session.add(task)
        db.session.commit()
        
        logging.info(f"Quick task added: {task_name} to project {project_id}")
        
        return jsonify({
            'success': True,
            'task': {
                'id': task.id,
                'name': task.name,
                'duration': task.duration,
                'status': task.status.name
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Quick task creation error: {str(e)}")
        return jsonify({'error': 'Failed to create task'}), 500

@project_mgmt_bp.route('/project/<int:project_id>/tasks')
@login_required
def project_tasks(project_id):
    """Get project tasks as JSON"""
    try:
        project = Project.query.get_or_404(project_id)
        if project.company_id != current_user.company_id:
            return jsonify({'error': 'Access denied'}), 403
        
        tasks = []
        for task in project.tasks:
            tasks.append({
                'id': task.id,
                'name': task.name,
                'start_date': task.start_date.isoformat(),
                'end_date': task.end_date.isoformat(),
                'duration': task.duration,
                'progress': task.progress,
                'status': task.status.name,
                'parent_id': task.parent_task_id
            })
        
        return jsonify({'tasks': tasks})
        
    except Exception as e:
        logging.error(f"Project tasks fetch error: {str(e)}")
        return jsonify({'error': 'Failed to fetch tasks'}), 500

@project_mgmt_bp.route('/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics via API"""
    try:
        stats = {
            'total_projects': Project.query.filter_by(company_id=current_user.company_id).count(),
            'active_projects': Project.query.filter_by(company_id=current_user.company_id, status='active').count(),
            'total_tasks': Task.query.join(Project).filter(Project.company_id == current_user.company_id).count(),
            'completed_tasks': Task.query.join(Project).filter(
                Project.company_id == current_user.company_id,
                Task.status == TaskStatus.COMPLETED
            ).count()
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logging.error(f"Dashboard stats error: {str(e)}")
        return jsonify({'error': 'Failed to fetch stats'}), 500