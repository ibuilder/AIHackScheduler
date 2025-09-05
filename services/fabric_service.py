import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Any
from models import Project, Task, Resource, AzureIntegration
from extensions import db

class FabricService:
    def __init__(self):
        self.workspace_id = os.getenv("FABRIC_WORKSPACE_ID")
        self.client_id = os.getenv("FABRIC_CLIENT_ID") 
        self.client_secret = os.getenv("FABRIC_CLIENT_SECRET")
        self.base_url = "https://api.fabric.microsoft.com"
        self._access_token = None

    def _get_access_token(self) -> str:
        """Get access token for Microsoft Fabric API."""
        if self._access_token:
            return self._access_token
            
        token_url = f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}/oauth2/v2.0/token"
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://api.fabric.microsoft.com/.default',
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data['access_token']
            return self._access_token
            
        except Exception as e:
            raise Exception(f"Failed to get Fabric access token: {str(e)}")

    def _make_api_request(self, endpoint: str, method: str = 'GET', data: Dict = None) -> Dict:
        """Make authenticated API request to Microsoft Fabric."""
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/v1/workspaces/{self.workspace_id}/{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            raise Exception(f"Fabric API request failed: {str(e)}")

    def sync_project_data(self, project_id: int) -> Dict[str, Any]:
        """Sync project data to Microsoft Fabric data lake."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        resources = Resource.query.filter_by(project_id=project_id).all()
        
        # Prepare project data for Fabric
        fabric_data = {
            'project': {
                'id': project.id,
                'name': project.name,
                'project_number': project.project_number,
                'start_date': project.start_date.isoformat(),
                'end_date': project.end_date.isoformat(),
                'budget': project.budget,
                'location': project.location,
                'status': project.status,
                'company_id': project.company_id,
                'sync_timestamp': datetime.utcnow().isoformat()
            },
            'tasks': [
                {
                    'id': task.id,
                    'name': task.name,
                    'project_id': task.project_id,
                    'start_date': task.start_date.isoformat(),
                    'end_date': task.end_date.isoformat(),
                    'duration': task.duration,
                    'progress': task.progress,
                    'status': task.status.name,
                    'location': task.location,
                    'wbs_code': task.wbs_code
                }
                for task in tasks
            ],
            'resources': [
                {
                    'id': resource.id,
                    'name': resource.name,
                    'type': resource.type,
                    'project_id': resource.project_id,
                    'unit_cost': resource.unit_cost,
                    'total_quantity': resource.total_quantity,
                    'available_quantity': resource.available_quantity
                }
                for resource in resources
            ]
        }
        
        try:
            # Create or update dataset in Fabric
            dataset_name = f"BBSchedule_Project_{project_id}"
            
            # Check if dataset exists
            try:
                dataset_info = self._make_api_request(f"datasets/{dataset_name}")
                # Dataset exists, update it
                result = self._make_api_request(
                    f"datasets/{dataset_name}/data",
                    method='PUT',
                    data=fabric_data
                )
            except:
                # Dataset doesn't exist, create it
                dataset_config = {
                    'name': dataset_name,
                    'description': f'Construction project data for {project.name}',
                    'schema': self._get_project_schema(),
                    'data': fabric_data
                }
                result = self._make_api_request(
                    'datasets',
                    method='POST',
                    data=dataset_config
                )
            
            return {
                'success': True,
                'dataset_name': dataset_name,
                'records_synced': {
                    'tasks': len(tasks),
                    'resources': len(resources)
                },
                'sync_timestamp': datetime.utcnow().isoformat(),
                'fabric_response': result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Fabric sync failed: {str(e)}",
                'project_id': project_id
            }

    def get_project_analytics(self, project_id: int) -> Dict[str, Any]:
        """Get analytics data from Microsoft Fabric for a project."""
        dataset_name = f"BBSchedule_Project_{project_id}"
        
        try:
            # Query Fabric for analytics
            analytics_query = {
                'query': f"""
                SELECT 
                    COUNT(tasks.id) as total_tasks,
                    AVG(tasks.progress) as avg_progress,
                    COUNT(CASE WHEN tasks.status = 'completed' THEN 1 END) as completed_tasks,
                    SUM(resources.unit_cost * resources.total_quantity) as total_resource_cost,
                    COUNT(DISTINCT tasks.location) as unique_locations
                FROM {dataset_name}.tasks 
                LEFT JOIN {dataset_name}.resources ON tasks.project_id = resources.project_id
                WHERE tasks.project_id = {project_id}
                """,
                'parameters': {'project_id': project_id}
            }
            
            analytics_result = self._make_api_request(
                f"datasets/{dataset_name}/query",
                method='POST',
                data=analytics_query
            )
            
            return {
                'success': True,
                'analytics': analytics_result,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Analytics query failed: {str(e)}"
            }

    def _get_project_schema(self) -> Dict:
        """Get the schema definition for project data in Fabric."""
        return {
            'project': {
                'id': 'integer',
                'name': 'string',
                'project_number': 'string',
                'start_date': 'date',
                'end_date': 'date',
                'budget': 'decimal',
                'location': 'string',
                'status': 'string',
                'company_id': 'integer',
                'sync_timestamp': 'datetime'
            },
            'tasks': {
                'id': 'integer',
                'name': 'string',
                'project_id': 'integer',
                'start_date': 'date',
                'end_date': 'date',
                'duration': 'integer',
                'progress': 'decimal',
                'status': 'string',
                'location': 'string',
                'wbs_code': 'string'
            },
            'resources': {
                'id': 'integer',
                'name': 'string',
                'type': 'string',
                'project_id': 'integer',
                'unit_cost': 'decimal',
                'total_quantity': 'decimal',
                'available_quantity': 'decimal'
            }
        }

    def create_data_pipeline(self, project_id: int, pipeline_config: Dict) -> Dict[str, Any]:
        """Create automated data pipeline for continuous project data sync."""
        pipeline_name = f"BBSchedule_Pipeline_{project_id}"
        
        pipeline_definition = {
            'name': pipeline_name,
            'description': f'Automated data sync pipeline for project {project_id}',
            'schedule': pipeline_config.get('schedule', 'daily'),
            'source': {
                'type': 'database',
                'connection_string': os.getenv('DATABASE_URL'),
                'query': f"""
                    SELECT p.*, t.*, r.* 
                    FROM projects p
                    LEFT JOIN tasks t ON p.id = t.project_id
                    LEFT JOIN resources r ON p.id = r.project_id
                    WHERE p.id = {project_id}
                """
            },
            'destination': {
                'type': 'fabric_dataset',
                'workspace_id': self.workspace_id,
                'dataset_name': f"BBSchedule_Project_{project_id}"
            },
            'transformations': pipeline_config.get('transformations', [])
        }
        
        try:
            result = self._make_api_request(
                'dataPipelines',
                method='POST',
                data=pipeline_definition
            )
            
            return {
                'success': True,
                'pipeline_id': result.get('id'),
                'pipeline_name': pipeline_name,
                'created_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Pipeline creation failed: {str(e)}"
            }
