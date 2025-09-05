from flask import Blueprint, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
import requests
import json
from datetime import datetime, timedelta
from models import Project, Task, PowerBIIntegration, TaskStatus
from extensions import db
import logging

powerbi_bp = Blueprint('powerbi', __name__)

class PowerBIClient:
    def __init__(self, client_id=None, client_secret=None, tenant_id=None):
        self.client_id = client_id
        self.client_secret = client_secret  
        self.tenant_id = tenant_id
        self.access_token = None
        self.token_expires = None
        self.base_url = "https://api.powerbi.com/v1.0/myorg"
        
    def get_access_token(self):
        """Get OAuth2 access token for Power BI API"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
            
        auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://analysis.windows.net/powerbi/api/.default'
        }
        
        try:
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            # Set expiry time (subtract 5 minutes for safety)
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in - 300)
            
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Power BI authentication failed: {str(e)}")
            return None
    
    def get_workspaces(self):
        """Get list of Power BI workspaces"""
        token = self.get_access_token()
        if not token:
            return None
            
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            response = requests.get(f"{self.base_url}/groups", headers=headers)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get Power BI workspaces: {str(e)}")
            return None
    
    def get_datasets(self, workspace_id):
        """Get datasets from a specific workspace"""
        token = self.get_access_token()
        if not token:
            return None
            
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            response = requests.get(f"{self.base_url}/groups/{workspace_id}/datasets", headers=headers)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get Power BI datasets: {str(e)}")
            return None
    
    def execute_query(self, workspace_id, dataset_id, dax_query):
        """Execute a DAX query against a Power BI dataset"""
        token = self.get_access_token()
        if not token:
            return None
            
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        query_data = {
            "queries": [
                {
                    "query": dax_query
                }
            ]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/groups/{workspace_id}/datasets/{dataset_id}/executeQueries",
                headers=headers,
                json=query_data
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to execute Power BI query: {str(e)}")
            return None

@powerbi_bp.route('/sync-projects')
@login_required
def sync_projects():
    """Sync project data from Power BI"""
    try:
        # Get Power BI credentials from environment or database
        import os
        client_id = os.environ.get('POWERBI_CLIENT_ID')
        client_secret = os.environ.get('POWERBI_CLIENT_SECRET')  
        tenant_id = os.environ.get('POWERBI_TENANT_ID')
        
        if not all([client_id, client_secret, tenant_id]):
            return jsonify({
                'error': 'Power BI credentials not configured',
                'missing': 'Please set POWERBI_CLIENT_ID, POWERBI_CLIENT_SECRET, and POWERBI_TENANT_ID'
            }), 400
        
        client = PowerBIClient(client_id, client_secret, tenant_id)
        
        # Extract workspace ID from the provided URL
        workspace_id = "64ee0127-6557-4496-aaf3-8f5551424a25"
        
        # Get datasets in the workspace
        datasets = client.get_datasets(workspace_id)
        if not datasets:
            return jsonify({'error': 'Failed to get datasets from Power BI'}), 500
        
        # Find project-related dataset (you may need to adjust this logic)
        project_dataset = None
        for dataset in datasets.get('value', []):
            if 'project' in dataset.get('name', '').lower():
                project_dataset = dataset
                break
        
        if not project_dataset:
            return jsonify({'error': 'No project dataset found in workspace'}), 404
        
        # Execute query to get project data
        dax_query = """
        EVALUATE
        SELECTCOLUMNS(
            Projects,
            "ProjectName", Projects[Name],
            "ProjectNumber", Projects[Number],
            "StartDate", Projects[StartDate],
            "EndDate", Projects[EndDate],
            "Budget", Projects[Budget],
            "Status", Projects[Status],
            "Location", Projects[Location]
        )
        """
        
        result = client.execute_query(workspace_id, project_dataset['id'], dax_query)
        if not result:
            return jsonify({'error': 'Failed to execute query'}), 500
        
        # Process and sync the data
        synced_projects = []
        
        for query_result in result.get('results', []):
            tables = query_result.get('tables', [])
            for table in tables:
                rows = table.get('rows', [])
                for row in rows:
                    project_data = dict(zip(
                        [col['name'] for col in table.get('columns', [])],
                        row
                    ))
                    
                    # Check if project already exists
                    existing_project = Project.query.filter_by(
                        project_number=project_data.get('ProjectNumber'),
                        company_id=current_user.company_id
                    ).first()
                    
                    if existing_project:
                        # Update existing project
                        existing_project.name = project_data.get('ProjectName')
                        existing_project.budget = project_data.get('Budget')
                        existing_project.location = project_data.get('Location')
                        synced_projects.append(existing_project.name)
                    else:
                        # Create new project
                        new_project = Project()
                        new_project.name = project_data.get('ProjectName')
                        new_project.project_number = project_data.get('ProjectNumber')
                        new_project.company_id = current_user.company_id
                        new_project.created_by = current_user.id
                        new_project.budget = project_data.get('Budget')
                        new_project.location = project_data.get('Location')
                        
                        # Parse dates if available
                        try:
                            if project_data.get('StartDate'):
                                new_project.start_date = datetime.strptime(
                                    project_data['StartDate'], '%Y-%m-%d'
                                ).date()
                            if project_data.get('EndDate'):
                                new_project.end_date = datetime.strptime(
                                    project_data['EndDate'], '%Y-%m-%d'
                                ).date()
                        except ValueError:
                            logging.warning(f"Invalid date format in Power BI data for project {project_data.get('ProjectName')}")
                        
                        db.session.add(new_project)
                        synced_projects.append(new_project.name)
        
        # Log the sync operation
        sync_record = PowerBIIntegration()
        sync_record.workspace_id = workspace_id
        sync_record.sync_status = 'completed'
        sync_record.sync_timestamp = datetime.now()
        sync_record.records_synced = len(synced_projects)
        sync_record.company_id = current_user.company_id
        
        db.session.add(sync_record)
        db.session.commit()
        
        logging.info(f"Power BI sync completed: {len(synced_projects)} projects synced")
        
        return jsonify({
            'success': True,
            'message': f'Successfully synced {len(synced_projects)} projects from Power BI',
            'projects': synced_projects
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Power BI sync error: {str(e)}")
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500

@powerbi_bp.route('/test-connection')
@login_required 
def test_connection():
    """Test Power BI API connection"""
    try:
        import os
        client_id = os.environ.get('POWERBI_CLIENT_ID')
        client_secret = os.environ.get('POWERBI_CLIENT_SECRET')
        tenant_id = os.environ.get('POWERBI_TENANT_ID')
        
        if not all([client_id, client_secret, tenant_id]):
            return jsonify({
                'success': False,
                'error': 'Power BI credentials not configured'
            })
        
        client = PowerBIClient(client_id, client_secret, tenant_id)
        
        # Test authentication
        token = client.get_access_token()
        if not token:
            return jsonify({
                'success': False,
                'error': 'Failed to authenticate with Power BI'
            })
        
        # Test workspace access
        workspace_id = "64ee0127-6557-4496-aaf3-8f5551424a25"
        datasets = client.get_datasets(workspace_id)
        
        return jsonify({
            'success': True,
            'message': 'Power BI connection successful',
            'workspace_id': workspace_id,
            'datasets_found': len(datasets.get('value', [])) if datasets else 0
        })
        
    except Exception as e:
        logging.error(f"Power BI connection test failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@powerbi_bp.route('/sync-status')
@login_required
def sync_status():
    """Get Power BI sync status and history"""
    try:
        recent_syncs = PowerBIIntegration.query.filter_by(
            company_id=current_user.company_id
        ).order_by(PowerBIIntegration.sync_timestamp.desc()).limit(10).all()
        
        sync_history = []
        for sync in recent_syncs:
            sync_history.append({
                'timestamp': sync.sync_timestamp.isoformat(),
                'status': sync.sync_status,
                'records_synced': sync.records_synced,
                'workspace_id': sync.workspace_id
            })
        
        return jsonify({
            'success': True,
            'sync_history': sync_history
        })
        
    except Exception as e:
        logging.error(f"Power BI sync status error: {str(e)}")
        return jsonify({'error': str(e)}), 500