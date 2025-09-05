import os
import json
from datetime import datetime
from celery import current_task
from tasks.celery_config import celery_app
from services.azure_ai import AzureAIService
from services.fabric_service import FabricService
from services.foundry_service import FoundryService

@celery_app.task(bind=True)
def process_project_file(self, project_id, file_path, file_type):
    """Process uploaded project files in background."""
    try:
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Starting file processing...'}
        )
        
        # Import models here to avoid circular imports
        from models import Project, Task, Resource
        from extensions import db
        
        project = Project.query.get(project_id)
        if not project:
            raise Exception(f"Project {project_id} not found")
        
        self.update_state(
            state='PROGRESS',
            meta={'current': 25, 'total': 100, 'status': 'Reading file...'}
        )
        
        # Process different file types
        if file_type == 'msp':
            tasks_data = process_msp_file(file_path)
        elif file_type == 'csv':
            tasks_data = process_csv_file(file_path)
        elif file_type == 'excel':
            tasks_data = process_excel_file(file_path)
        else:
            raise Exception(f"Unsupported file type: {file_type}")
        
        self.update_state(
            state='PROGRESS',
            meta={'current': 50, 'total': 100, 'status': 'Creating tasks...'}
        )
        
        # Create tasks from processed data
        created_tasks = []
        for task_data in tasks_data:
            task = Task(
                name=task_data['name'],
                description=task_data.get('description', ''),
                project_id=project_id,
                start_date=task_data['start_date'],
                end_date=task_data['end_date'],
                duration=task_data['duration'],
                wbs_code=task_data.get('wbs_code'),
                location=task_data.get('location')
            )
            db.session.add(task)
            created_tasks.append(task)
        
        db.session.commit()
        
        self.update_state(
            state='PROGRESS',
            meta={'current': 100, 'total': 100, 'status': 'File processing complete'}
        )
        
        return {
            'status': 'completed',
            'tasks_created': len(created_tasks),
            'file_path': file_path
        }
        
    except Exception as exc:
        self.update_state(
            state='FAILURE',
            meta={'current': 0, 'total': 100, 'status': str(exc)}
        )
        raise exc

@celery_app.task(bind=True)
def sync_azure_services(self, project_id, services=['ai', 'fabric', 'foundry']):
    """Sync project data with Azure services."""
    try:
        from models import Project, AzureIntegration
        from extensions import db
        
        project = Project.query.get(project_id)
        if not project:
            raise Exception(f"Project {project_id} not found")
        
        total_services = len(services)
        results = {}
        
        for i, service in enumerate(services):
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': i + 1,
                    'total': total_services,
                    'status': f'Syncing with Azure {service.upper()}...'
                }
            )
            
            try:
                if service == 'ai':
                    ai_service = AzureAIService()
                    results['ai'] = ai_service.analyze_project_schedule(project_id)
                
                elif service == 'fabric':
                    fabric_service = FabricService()
                    results['fabric'] = fabric_service.sync_project_data(project_id)
                
                elif service == 'foundry':
                    foundry_service = FoundryService()
                    results['foundry'] = foundry_service.predict_project_outcomes(
                        project_id, 'completion_date'
                    )
                
                # Update integration status
                integration = AzureIntegration.query.filter_by(
                    project_id=project_id,
                    service_type=service
                ).first()
                
                if integration:
                    integration.last_sync = datetime.utcnow()
                    integration.sync_status = 'completed'
                    db.session.commit()
                
            except Exception as service_error:
                results[service] = {'success': False, 'error': str(service_error)}
        
        return {
            'status': 'completed',
            'project_id': project_id,
            'results': results
        }
        
    except Exception as exc:
        self.update_state(
            state='FAILURE',
            meta={'status': str(exc)}
        )
        raise exc

@celery_app.task
def generate_project_report(project_id, report_type='comprehensive'):
    """Generate detailed project reports."""
    try:
        from models import Project, Task, Resource
        from extensions import db
        
        project = Project.query.get(project_id)
        if not project:
            raise Exception(f"Project {project_id} not found")
        
        tasks = Task.query.filter_by(project_id=project_id).all()
        resources = Resource.query.filter_by(project_id=project_id).all()
        
        # Generate report data
        report_data = {
            'project_info': {
                'id': project.id,
                'name': project.name,
                'start_date': project.start_date.isoformat(),
                'end_date': project.end_date.isoformat(),
                'budget': project.budget,
                'status': project.status
            },
            'tasks_summary': {
                'total_tasks': len(tasks),
                'completed_tasks': len([t for t in tasks if t.status.name == 'COMPLETED']),
                'in_progress_tasks': len([t for t in tasks if t.status.name == 'IN_PROGRESS']),
                'not_started_tasks': len([t for t in tasks if t.status.name == 'NOT_STARTED'])
            },
            'resources_summary': {
                'total_resources': len(resources),
                'labor_resources': len([r for r in resources if r.type == 'labor']),
                'equipment_resources': len([r for r in resources if r.type == 'equipment']),
                'material_resources': len([r for r in resources if r.type == 'material'])
            },
            'generated_at': datetime.utcnow().isoformat()
        }
        
        # Save report or send notification
        return {
            'status': 'completed',
            'report_data': report_data
        }
        
    except Exception as exc:
        raise exc

@celery_app.task
def send_notification(user_id, notification_type, data):
    """Send notifications to users."""
    try:
        from models import User
        
        user = User.query.get(user_id)
        if not user:
            return {'status': 'failed', 'error': 'User not found'}
        
        # Here you would integrate with email service, SMS, push notifications, etc.
        notification_data = {
            'user_email': user.email,
            'type': notification_type,
            'data': data,
            'sent_at': datetime.utcnow().isoformat()
        }
        
        # For now, just log the notification
        print(f"Notification sent: {json.dumps(notification_data)}")
        
        return {
            'status': 'completed',
            'notification': notification_data
        }
        
    except Exception as exc:
        return {'status': 'failed', 'error': str(exc)}

# Helper functions for file processing
def process_msp_file(file_path):
    """Process Microsoft Project file."""
    # This would use a library like python-msp to parse MSP files
    # For now, return mock data
    return [
        {
            'name': 'Foundation Work',
            'start_date': datetime.now().date(),
            'end_date': datetime.now().date(),
            'duration': 5,
            'wbs_code': '1.1'
        }
    ]

def process_csv_file(file_path):
    """Process CSV file with task data."""
    import csv
    tasks = []
    
    with open(file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            tasks.append({
                'name': row.get('Task Name', ''),
                'start_date': datetime.strptime(row.get('Start Date', ''), '%Y-%m-%d').date(),
                'end_date': datetime.strptime(row.get('End Date', ''), '%Y-%m-%d').date(),
                'duration': int(row.get('Duration', 1)),
                'wbs_code': row.get('WBS Code', ''),
                'location': row.get('Location', '')
            })
    
    return tasks

def process_excel_file(file_path):
    """Process Excel file with task data."""
    import openpyxl
    
    workbook = openpyxl.load_workbook(file_path)
    sheet = workbook.active
    
    tasks = []
    for row in sheet.iter_rows(min_row=2, values_only=True):  # Skip header
        if row[0]:  # Task name exists
            tasks.append({
                'name': row[0],
                'start_date': row[1] if isinstance(row[1], date) else datetime.strptime(str(row[1]), '%Y-%m-%d').date(),
                'end_date': row[2] if isinstance(row[2], date) else datetime.strptime(str(row[2]), '%Y-%m-%d').date(),
                'duration': int(row[3]) if row[3] else 1,
                'wbs_code': row[4] if len(row) > 4 else '',
                'location': row[5] if len(row) > 5 else ''
            })
    
    return tasks
