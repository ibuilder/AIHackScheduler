import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any
from models import Project, Task, TaskStatus
from extensions import db

class FoundryService:
    def __init__(self):
        self.endpoint = os.getenv("FOUNDRY_ENDPOINT")
        self.api_key = os.getenv("FOUNDRY_API_KEY")
        self.model_name = os.getenv("FOUNDRY_MODEL_NAME", "gpt-4")

    def _make_foundry_request(self, endpoint: str, data: Dict) -> Dict:
        """Make request to Azure AI Foundry."""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.endpoint}/{endpoint}"
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            raise Exception(f"Foundry API request failed: {str(e)}")

    def predict_project_outcomes(self, project_id: int, prediction_type: str) -> Dict[str, Any]:
        """Predict project outcomes using Azure AI Foundry."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        # Prepare historical data for prediction
        project_features = {
            'project_duration_days': (project.end_date - project.start_date).days,
            'total_tasks': len(tasks),
            'budget': project.budget,
            'completed_tasks': len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
            'in_progress_tasks': len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            'overdue_tasks': len([
                t for t in tasks 
                if t.end_date < datetime.now().date() and t.status != TaskStatus.COMPLETED
            ]),
            'current_progress': sum(t.progress for t in tasks) / len(tasks) if tasks else 0,
            'days_elapsed': (datetime.now().date() - project.start_date).days,
            'location_complexity': len(set(t.location for t in tasks if t.location)),
            'schedule_type': project.schedule_type.name
        }
        
        prediction_request = {
            'model': self.model_name,
            'prediction_type': prediction_type,
            'features': project_features,
            'historical_context': {
                'industry': 'construction',
                'project_type': 'general_contracting',
                'company': 'balfour_beatty'
            }
        }
        
        try:
            if prediction_type == 'completion_date':
                return self._predict_completion_date(prediction_request)
            elif prediction_type == 'budget_variance':
                return self._predict_budget_variance(prediction_request)
            elif prediction_type == 'risk_assessment':
                return self._predict_risks(prediction_request)
            elif prediction_type == 'resource_needs':
                return self._predict_resource_needs(prediction_request)
            else:
                raise ValueError(f"Unsupported prediction type: {prediction_type}")
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Prediction failed: {str(e)}"
            }

    def _predict_completion_date(self, request_data: Dict) -> Dict[str, Any]:
        """Predict project completion date."""
        completion_prompt = {
            'messages': [
                {
                    'role': 'system',
                    'content': '''You are an AI construction project completion predictor. 
                    Analyze project features and predict completion dates with high accuracy.
                    Consider industry standards, seasonal factors, and typical delays.'''
                },
                {
                    'role': 'user',
                    'content': f'''
                    Predict completion date for this construction project:
                    
                    Features: {json.dumps(request_data['features'], indent=2)}
                    
                    Provide:
                    1. Predicted completion date
                    2. Confidence level (0-100%)
                    3. Key factors affecting prediction
                    4. Potential delays and mitigation strategies
                    5. Best case and worst case scenarios
                    
                    Return as structured JSON.
                    '''
                }
            ],
            'max_tokens': 1500,
            'temperature': 0.2
        }
        
        try:
            result = self._make_foundry_request('chat/completions', completion_prompt)
            prediction = json.loads(result['choices'][0]['message']['content'])
            
            return {
                'success': True,
                'prediction_type': 'completion_date',
                'results': prediction,
                'features_used': request_data['features'],
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Completion date prediction failed: {str(e)}"
            }

    def _predict_budget_variance(self, request_data: Dict) -> Dict[str, Any]:
        """Predict budget variance and cost overruns."""
        budget_prompt = {
            'messages': [
                {
                    'role': 'system',
                    'content': '''You are a construction cost prediction expert. 
                    Analyze projects and predict budget variances with high accuracy.
                    Consider material costs, labor rates, and market conditions.'''
                },
                {
                    'role': 'user',
                    'content': f'''
                    Predict budget variance for this construction project:
                    
                    Features: {json.dumps(request_data['features'], indent=2)}
                    
                    Provide:
                    1. Expected budget variance percentage
                    2. Confidence level
                    3. Cost drivers and risk factors
                    4. Recommended contingency percentage
                    5. Cost control strategies
                    
                    Return as structured JSON.
                    '''
                }
            ],
            'max_tokens': 1500,
            'temperature': 0.1
        }
        
        try:
            result = self._make_foundry_request('chat/completions', budget_prompt)
            prediction = json.loads(result['choices'][0]['message']['content'])
            
            return {
                'success': True,
                'prediction_type': 'budget_variance',
                'results': prediction,
                'features_used': request_data['features'],
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Budget variance prediction failed: {str(e)}"
            }

    def _predict_risks(self, request_data: Dict) -> Dict[str, Any]:
        """Predict project risks and mitigation strategies."""
        risk_prompt = {
            'messages': [
                {
                    'role': 'system',
                    'content': '''You are a construction risk assessment expert.
                    Identify potential risks and provide mitigation strategies.
                    Focus on schedule, budget, quality, and safety risks.'''
                },
                {
                    'role': 'user',
                    'content': f'''
                    Assess risks for this construction project:
                    
                    Features: {json.dumps(request_data['features'], indent=2)}
                    
                    Identify:
                    1. High, medium, and low probability risks
                    2. Impact assessment for each risk
                    3. Mitigation strategies
                    4. Early warning indicators
                    5. Contingency plans
                    
                    Return as structured JSON with risk matrix.
                    '''
                }
            ],
            'max_tokens': 2000,
            'temperature': 0.3
        }
        
        try:
            result = self._make_foundry_request('chat/completions', risk_prompt)
            prediction = json.loads(result['choices'][0]['message']['content'])
            
            return {
                'success': True,
                'prediction_type': 'risk_assessment',
                'results': prediction,
                'features_used': request_data['features'],
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Risk assessment failed: {str(e)}"
            }

    def _predict_resource_needs(self, request_data: Dict) -> Dict[str, Any]:
        """Predict future resource requirements."""
        resource_prompt = {
            'messages': [
                {
                    'role': 'system',
                    'content': '''You are a construction resource planning expert.
                    Predict resource needs based on project progress and upcoming tasks.
                    Consider labor, equipment, and material requirements.'''
                },
                {
                    'role': 'user',
                    'content': f'''
                    Predict resource needs for this construction project:
                    
                    Features: {json.dumps(request_data['features'], indent=2)}
                    
                    Forecast:
                    1. Labor requirements by trade
                    2. Equipment needs and utilization
                    3. Material delivery schedules
                    4. Peak resource periods
                    5. Resource optimization opportunities
                    
                    Return as structured JSON with timeline.
                    '''
                }
            ],
            'max_tokens': 1800,
            'temperature': 0.2
        }
        
        try:
            result = self._make_foundry_request('chat/completions', resource_prompt)
            prediction = json.loads(result['choices'][0]['message']['content'])
            
            return {
                'success': True,
                'prediction_type': 'resource_needs',
                'results': prediction,
                'features_used': request_data['features'],
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Resource prediction failed: {str(e)}"
            }

    def generate_schedule_insights(self, project_id: int) -> Dict[str, Any]:
        """Generate comprehensive schedule insights using Foundry."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        insights_request = {
            'model': self.model_name,
            'project_data': {
                'name': project.name,
                'schedule_type': project.schedule_type.name,
                'task_count': len(tasks),
                'progress_data': [
                    {
                        'task_name': task.name,
                        'progress': task.progress,
                        'status': task.status.name,
                        'duration': task.duration
                    }
                    for task in tasks
                ]
            }
        }
        
        insights_prompt = {
            'messages': [
                {
                    'role': 'system',
                    'content': '''You are a construction scheduling insights expert.
                    Analyze project schedules and provide actionable recommendations.
                    Focus on optimization, efficiency, and best practices.'''
                },
                {
                    'role': 'user',
                    'content': f'''
                    Generate schedule insights for this project:
                    
                    {json.dumps(insights_request['project_data'], indent=2)}
                    
                    Provide:
                    1. Schedule health assessment
                    2. Critical path optimization
                    3. Task sequencing improvements
                    4. Resource leveling opportunities
                    5. Performance benchmarks
                    6. Actionable recommendations
                    
                    Return as structured JSON with priorities.
                    '''
                }
            ],
            'max_tokens': 2500,
            'temperature': 0.3
        }
        
        try:
            result = self._make_foundry_request('chat/completions', insights_prompt)
            insights = json.loads(result['choices'][0]['message']['content'])
            
            return {
                'success': True,
                'insights': insights,
                'project_id': project_id,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Schedule insights generation failed: {str(e)}"
            }
