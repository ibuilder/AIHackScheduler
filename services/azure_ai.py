import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from openai import AzureOpenAI
from models import Project, Task, Resource, TaskStatus
from extensions import db

class AzureAIService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("FOUNDRY_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.getenv("FOUNDRY_ENDPOINT")
        )
        self.model_name = os.getenv("FOUNDRY_MODEL_NAME", "gpt-4")

    def analyze_project_schedule(self, project_id: int) -> Dict[str, Any]:
        """Analyze project schedule using Azure AI."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        # Prepare data for AI analysis
        project_data = {
            'project_name': project.name,
            'start_date': project.start_date.isoformat(),
            'end_date': project.end_date.isoformat(),
            'total_tasks': len(tasks),
            'tasks': [
                {
                    'name': task.name,
                    'start_date': task.start_date.isoformat(),
                    'end_date': task.end_date.isoformat(),
                    'duration': task.duration,
                    'progress': task.progress,
                    'status': task.status.name
                }
                for task in tasks
            ]
        }
        
        prompt = f"""
        Analyze the following construction project schedule and provide insights:
        
        {json.dumps(project_data, indent=2)}
        
        Please provide:
        1. Risk assessment (high, medium, low risks)
        2. Critical path analysis
        3. Resource bottlenecks
        4. Schedule optimization recommendations
        5. Completion probability estimate
        
        Return your analysis as a structured JSON response.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a construction scheduling expert AI assistant specializing in project analysis and optimization."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
            return {
                'success': True,
                'analysis': analysis,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Azure AI analysis failed: {str(e)}"
            }

    def optimize_schedule(self, project_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize project schedule using AI recommendations."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        optimization_type = parameters.get('type', 'time')
        constraints = parameters.get('constraints', {})
        
        project_data = {
            'project_name': project.name,
            'optimization_type': optimization_type,
            'constraints': constraints,
            'tasks': [
                {
                    'id': task.id,
                    'name': task.name,
                    'start_date': task.start_date.isoformat(),
                    'end_date': task.end_date.isoformat(),
                    'duration': task.duration,
                    'progress': task.progress,
                    'status': task.status.name,
                    'dependencies': [dep.predecessor_task_id for dep in task.dependencies]
                }
                for task in tasks
            ]
        }
        
        prompt = f"""
        Optimize the following construction project schedule:
        
        {json.dumps(project_data, indent=2)}
        
        Optimization objective: {optimization_type}
        
        Please provide:
        1. Recommended task sequence changes
        2. Duration adjustments
        3. Resource reallocation suggestions
        4. Expected time/cost savings
        5. Risk mitigation strategies
        
        Return specific actionable recommendations as a structured JSON response.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a construction project optimization expert. Provide practical, implementable recommendations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2500,
                temperature=0.2
            )
            
            optimization = json.loads(response.choices[0].message.content)
            
            return {
                'success': True,
                'optimization': optimization,
                'parameters': parameters,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Schedule optimization failed: {str(e)}"
            }

    def predict_completion_date(self, project_id: int) -> Dict[str, Any]:
        """Predict project completion date using AI."""
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        # Calculate current progress
        total_progress = sum(task.progress for task in tasks) / len(tasks) if tasks else 0
        completed_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        remaining_tasks = len(tasks) - completed_tasks
        
        project_metrics = {
            'total_tasks': len(tasks),
            'completed_tasks': completed_tasks,
            'remaining_tasks': remaining_tasks,
            'overall_progress': total_progress,
            'planned_end_date': project.end_date.isoformat(),
            'days_elapsed': (datetime.now().date() - project.start_date).days,
            'total_planned_days': (project.end_date - project.start_date).days
        }
        
        prompt = f"""
        Predict the completion date for this construction project:
        
        {json.dumps(project_metrics, indent=2)}
        
        Consider:
        1. Current progress rate
        2. Remaining work complexity
        3. Typical construction delays
        4. Seasonal factors
        5. Resource availability
        
        Provide a realistic completion date prediction with confidence level.
        Return as structured JSON with date prediction and confidence score.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a construction project forecasting expert with deep knowledge of project completion patterns."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            prediction = json.loads(response.choices[0].message.content)
            
            return {
                'success': True,
                'prediction': prediction,
                'current_metrics': project_metrics,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Completion prediction failed: {str(e)}"
            }
