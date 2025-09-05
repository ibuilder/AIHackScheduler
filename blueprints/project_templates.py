from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Project, Task, TaskStatus
from extensions import db
from templates.projects.templates import ConstructionProjectTemplates
from audit.audit_logger import audit_logger
import logging

project_templates_bp = Blueprint('project_templates', __name__)

@project_templates_bp.route('/templates')
@login_required
def template_gallery():
    """Display available project templates"""
    templates = ConstructionProjectTemplates.get_available_templates()
    return render_template('projects/template_gallery.html', templates=templates)

@project_templates_bp.route('/templates/<template_id>')
@login_required
def template_preview(template_id):
    """Preview a specific template"""
    try:
        template = ConstructionProjectTemplates.get_template(template_id)
        metrics = ConstructionProjectTemplates.calculate_project_metrics(template)
        
        return render_template('projects/template_preview.html', 
                             template=template, 
                             template_id=template_id,
                             metrics=metrics)
    except ValueError as e:
        flash(f'Template not found: {str(e)}', 'error')
        return redirect(url_for('project_templates.template_gallery'))

@project_templates_bp.route('/templates/<template_id>/create', methods=['GET', 'POST'])
@login_required
def create_from_template(template_id):
    """Create a new project from template"""
    try:
        template = ConstructionProjectTemplates.get_template(template_id)
        
        if request.method == 'POST':
            # Get form data
            project_name = request.form.get('project_name')
            project_description = request.form.get('project_description')
            project_location = request.form.get('project_location')
            client_name = request.form.get('client_name')
            budget = request.form.get('budget')
            start_date_str = request.form.get('start_date')
            
            if not all([project_name, project_location, start_date_str]):
                flash('Please fill in all required fields', 'error')
                return render_template('projects/create_from_template.html', 
                                     template=template, 
                                     template_id=template_id)
            
            try:
                from datetime import datetime
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                
                # Create the project
                project = Project()
                project.name = project_name
                project.description = project_description or template.get('description', '')
                project.location = project_location
                project.client_name = client_name
                project.budget = float(budget) if budget else None
                project.start_date = start_date
                project.company_id = current_user.company_id
                project.created_by = current_user.id
                project.status = 'planning'
                project.template_used = template_id
                
                db.session.add(project)
                db.session.flush()  # Get project ID
                
                # Create tasks from template
                task_map = {}  # Track created tasks for dependency resolution
                
                for template_task in template.get('tasks', []):
                    task = Task()
                    task.name = template_task['name']
                    task.description = template_task.get('description', '')
                    task.project_id = project.id
                    task.duration = template_task.get('duration', 1)
                    # Set priority based on string value
                    priority_str = template_task.get('priority', 'MEDIUM')
                    if priority_str == 'HIGH':
                        task.priority = 'high'
                    elif priority_str == 'LOW':
                        task.priority = 'low'
                    else:
                        task.priority = 'medium'
                    task.status = TaskStatus.NOT_STARTED
                    task.phase = template_task.get('phase', 'General')
                    
                    # Calculate dates relative to project start
                    task_start_offset = (template_task['start_date'] - template.get('tasks')[0]['start_date']).days
                    task.start_date = start_date + timedelta(days=task_start_offset)
                    task.end_date = task.start_date + timedelta(days=task.duration)
                    
                    db.session.add(task)
                    task_map[template_task['name']] = task
                
                # Handle dependencies (simplified - would need more complex logic for full dependency management)
                for template_task in template.get('tasks', []):
                    if 'dependencies' in template_task:
                        current_task = task_map.get(template_task['name'])
                        for dep_name in template_task['dependencies']:
                            dependency_task = task_map.get(dep_name)
                            if current_task and dependency_task:
                                # Adjust start date based on dependency
                                if current_task.start_date <= dependency_task.end_date:
                                    current_task.start_date = dependency_task.end_date + timedelta(days=1)
                                    current_task.end_date = current_task.start_date + timedelta(days=current_task.duration)
                
                # Calculate project end date
                if task_map:
                    project.end_date = max(task.end_date for task in task_map.values())
                
                db.session.commit()
                
                # Log project creation
                audit_logger.log_project_action('project_created_from_template', project.id, {
                    'template_id': template_id,
                    'task_count': len(task_map)
                })
                
                flash(f'Project "{project_name}" created successfully from template!', 'success')
                return redirect(url_for('projects.detail', project_id=project.id))
                
            except ValueError as e:
                flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
            except Exception as e:
                db.session.rollback()
                logging.error(f"Error creating project from template: {str(e)}")
                flash('Error creating project. Please try again.', 'error')
        
        return render_template('projects/create_from_template.html', 
                             template=template, 
                             template_id=template_id)
                             
    except ValueError as e:
        flash(f'Template not found: {str(e)}', 'error')
        return redirect(url_for('project_templates.template_gallery'))

@project_templates_bp.route('/api/templates')
@login_required
def api_templates():
    """API endpoint for templates data"""
    templates = ConstructionProjectTemplates.get_available_templates()
    return jsonify(templates)

@project_templates_bp.route('/api/templates/<template_id>')
@login_required
def api_template_detail(template_id):
    """API endpoint for specific template details"""
    try:
        template = ConstructionProjectTemplates.get_template(template_id)
        metrics = ConstructionProjectTemplates.calculate_project_metrics(template)
        
        return jsonify({
            'template': template,
            'metrics': metrics,
            'success': True
        })
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 404

@project_templates_bp.route('/api/templates/<template_id>/estimate', methods=['POST'])
@login_required
def api_estimate_project(template_id):
    """API endpoint to estimate project timeline and cost"""
    try:
        template = ConstructionProjectTemplates.get_template(template_id)
        
        # Get estimation parameters
        data = request.get_json()
        crew_size_factor = data.get('crew_size_factor', 1.0)
        complexity_factor = data.get('complexity_factor', 1.0)
        weather_factor = data.get('weather_factor', 1.0)
        
        # Calculate adjusted timeline
        base_duration = sum(task.get('duration', 0) for task in template.get('tasks', []))
        adjusted_duration = base_duration * complexity_factor * weather_factor / crew_size_factor
        
        # Estimate costs (simplified calculation)
        base_cost_per_day = 15000  # Base daily cost
        estimated_cost = adjusted_duration * base_cost_per_day
        
        return jsonify({
            'estimated_duration_days': round(adjusted_duration),
            'estimated_cost': round(estimated_cost),
            'crew_size_factor': crew_size_factor,
            'complexity_factor': complexity_factor,
            'weather_factor': weather_factor,
            'success': True
        })
        
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 404
    except Exception as e:
        return jsonify({
            'error': 'Estimation failed',
            'success': False
        }), 500

@project_templates_bp.route('/my-templates')
@login_required
def my_templates():
    """Show projects created from templates by current user"""
    projects = Project.query.filter_by(
        company_id=current_user.company_id,
        created_by=current_user.id
    ).filter(
        Project.template_used.isnot(None)
    ).order_by(Project.created_at.desc()).all()
    
    return render_template('projects/my_templates.html', projects=projects)

from datetime import timedelta