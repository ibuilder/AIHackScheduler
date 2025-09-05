from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Project, AzureIntegration
from extensions import db
from services.azure_ai import AzureAIService
from services.fabric_service import FabricService
from services.foundry_service import FoundryService
import json

azure_bp = Blueprint('azure', __name__)

@azure_bp.route('/dashboard')
@login_required
def dashboard():
    # Get Azure integrations for user's company
    integrations = AzureIntegration.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).all()
    
    return render_template('azure/dashboard.html', integrations=integrations)

@azure_bp.route('/ai/analyze/<int:project_id>')
@login_required
def analyze_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    ai_service = AzureAIService()
    
    try:
        analysis = ai_service.analyze_project_schedule(project_id)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@azure_bp.route('/ai/optimize/<int:project_id>')
@login_required
def ai_optimize(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    ai_service = AzureAIService()
    parameters = request.args.to_dict()
    
    try:
        optimization = ai_service.optimize_schedule(project_id, parameters)
        return jsonify(optimization)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@azure_bp.route('/fabric/sync/<int:project_id>')
@login_required
def fabric_sync(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    fabric_service = FabricService()
    
    try:
        sync_result = fabric_service.sync_project_data(project_id)
        
        # Update or create integration record
        integration = AzureIntegration.query.filter_by(
            project_id=project_id,
            service_type='fabric'
        ).first()
        
        if not integration:
            integration = AzureIntegration(
                project_id=project_id,
                service_type='fabric',
                workspace_id=project.fabric_dataset_id
            )
            db.session.add(integration)
        
        integration.last_sync = db.func.now()
        integration.sync_status = 'completed' if sync_result['success'] else 'failed'
        db.session.commit()
        
        return jsonify(sync_result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@azure_bp.route('/foundry/predict/<int:project_id>')
@login_required
def foundry_predict(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    foundry_service = FoundryService()
    prediction_type = request.args.get('type', 'completion_date')
    
    try:
        predictions = foundry_service.predict_project_outcomes(project_id, prediction_type)
        return jsonify(predictions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@azure_bp.route('/configure/<int:project_id>', methods=['GET', 'POST'])
@login_required
def configure_integration(project_id):
    project = Project.query.get_or_404(project_id)
    
    if current_user.company_id != project.company_id:
        flash('Access denied', 'error')
        return redirect(url_for('projects.list_projects'))
    
    if request.method == 'POST':
        service_type = request.form.get('service_type')
        
        # Update or create integration
        integration = AzureIntegration.query.filter_by(
            project_id=project_id,
            service_type=service_type
        ).first()
        
        if not integration:
            integration = AzureIntegration(
                project_id=project_id,
                service_type=service_type
            )
            db.session.add(integration)
        
        integration.endpoint_url = request.form.get('endpoint_url')
        integration.workspace_id = request.form.get('workspace_id')
        integration.configuration = json.loads(request.form.get('configuration', '{}'))
        
        db.session.commit()
        flash('Integration configured successfully', 'success')
        return redirect(url_for('azure.dashboard'))
    
    # Get existing integrations
    integrations = AzureIntegration.query.filter_by(project_id=project_id).all()
    
    return render_template('azure/configure.html', 
                         project=project, 
                         integrations=integrations)
