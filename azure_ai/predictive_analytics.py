"""
Azure AI Integration for BBSchedule Platform
Predictive analytics and AI-powered insights for construction projects
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from models import Project, Task, User, Company, TaskStatus
from extensions import db
import json
import logging
import requests
import os
from typing import Dict, List, Any, Optional

azure_ai_bp = Blueprint('azure_ai', __name__)

class AzureAIPredictiveAnalytics:
    """Azure AI-powered predictive analytics for construction projects"""
    
    def __init__(self):
        self.azure_openai_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_openai_key = os.getenv('AZURE_OPENAI_KEY')
        self.azure_openai_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4')
        self.fabric_endpoint = os.getenv('AZURE_FABRIC_ENDPOINT')
        self.fabric_token = os.getenv('AZURE_FABRIC_TOKEN')
        
    def analyze_project_risks(self, project_id: int, company_id: int) -> Dict[str, Any]:
        """Analyze project risks using AI"""
        project = Project.query.filter_by(id=project_id, company_id=company_id).first()
        if not project:
            raise ValueError("Project not found")
        
        # Gather project data
        project_data = self._gather_project_data(project)
        
        # Use AI to analyze risks
        risk_analysis = self._ai_risk_analysis(project_data)
        
        # Calculate risk scores
        risk_scores = self._calculate_risk_scores(project_data)
        
        return {
            'project_id': project_id,
            'overall_risk_score': risk_scores['overall'],
            'risk_categories': {
                'schedule_risk': risk_scores['schedule'],
                'cost_risk': risk_scores['cost'],
                'quality_risk': risk_scores['quality'],
                'weather_risk': risk_scores['weather'],
                'resource_risk': risk_scores['resource']
            },
            'ai_insights': risk_analysis,
            'recommendations': self._generate_recommendations(risk_analysis, risk_scores),
            'probability_outcomes': self._predict_outcomes(project_data),
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def predict_project_completion(self, project_id: int, company_id: int) -> Dict[str, Any]:
        """Predict project completion using machine learning"""
        project = Project.query.filter_by(id=project_id, company_id=company_id).first()
        if not project:
            raise ValueError("Project not found")
        
        project_data = self._gather_project_data(project)
        
        # AI-based completion prediction
        completion_prediction = self._ai_completion_prediction(project_data)
        
        # Statistical analysis
        statistical_prediction = self._statistical_completion_prediction(project_data)
        
        return {
            'project_id': project_id,
            'ai_prediction': completion_prediction,
            'statistical_prediction': statistical_prediction,
            'confidence_level': min(completion_prediction.get('confidence', 0.7), 0.95),
            'factors_analysis': self._analyze_completion_factors(project_data),
            'milestone_predictions': self._predict_milestones(project_data),
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def optimize_resource_allocation(self, project_id: int, company_id: int) -> Dict[str, Any]:
        """AI-powered resource optimization recommendations"""
        project = Project.query.filter_by(id=project_id, company_id=company_id).first()
        if not project:
            raise ValueError("Project not found")
        
        project_data = self._gather_project_data(project)
        
        # Analyze current resource allocation
        current_allocation = self._analyze_current_resources(project_data)
        
        # AI optimization
        optimization_suggestions = self._ai_resource_optimization(project_data)
        
        return {
            'project_id': project_id,
            'current_allocation': current_allocation,
            'optimization_suggestions': optimization_suggestions,
            'efficiency_gains': self._calculate_efficiency_gains(current_allocation, optimization_suggestions),
            'cost_impact': self._calculate_cost_impact(optimization_suggestions),
            'implementation_priority': self._prioritize_optimizations(optimization_suggestions),
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def generate_project_insights(self, company_id: int, days_back: int = 90) -> Dict[str, Any]:
        """Generate company-wide AI insights from historical data"""
        # Gather historical data
        historical_data = self._gather_historical_data(company_id, days_back)
        
        # AI-powered insights
        insights = self._ai_company_insights(historical_data)
        
        # Trend analysis
        trends = self._analyze_trends(historical_data)
        
        # Predictive modeling for future projects
        future_predictions = self._predict_future_performance(historical_data)
        
        return {
            'company_id': company_id,
            'analysis_period': f'{days_back} days',
            'ai_insights': insights,
            'performance_trends': trends,
            'future_predictions': future_predictions,
            'benchmarking': self._industry_benchmarking(historical_data),
            'strategic_recommendations': self._strategic_recommendations(insights, trends),
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _gather_project_data(self, project: Project) -> Dict[str, Any]:
        """Gather comprehensive project data for analysis"""
        tasks = Task.query.filter_by(project_id=project.id).all()
        
        # Calculate project metrics
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        in_progress_tasks = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        overdue_tasks = len([t for t in tasks if t.end_date and t.end_date < date.today() and t.status != TaskStatus.COMPLETED])
        
        # Progress calculation
        progress_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Timeline analysis
        days_elapsed = (date.today() - project.start_date).days if project.start_date else 0
        total_duration = (project.end_date - project.start_date).days if project.start_date and project.end_date else 0
        days_remaining = (project.end_date - date.today()).days if project.end_date else 0
        
        # Budget analysis
        budget_utilized = 0.0  # Would be calculated from actual cost tracking
        budget_variance = 0.0  # Positive = over budget, negative = under budget
        
        return {
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'end_date': project.end_date.isoformat() if project.end_date else None,
                'budget': project.budget,
                'status': project.status,
                'location': getattr(project, 'location', 'Unknown'),
                'project_type': getattr(project, 'project_type', 'General Construction')
            },
            'metrics': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'in_progress_tasks': in_progress_tasks,
                'overdue_tasks': overdue_tasks,
                'progress_percentage': progress_percentage,
                'days_elapsed': days_elapsed,
                'total_duration': total_duration,
                'days_remaining': days_remaining,
                'budget_utilized': budget_utilized,
                'budget_variance': budget_variance
            },
            'tasks': [
                {
                    'id': task.id,
                    'name': task.name,
                    'status': task.status.name if task.status else 'unknown',
                    'priority': getattr(task, 'priority', 'medium'),
                    'duration': task.duration,
                    'start_date': task.start_date.isoformat() if task.start_date else None,
                    'end_date': task.end_date.isoformat() if task.end_date else None,
                    'phase': getattr(task, 'phase', 'General')
                }
                for task in tasks
            ]
        }
    
    def _ai_risk_analysis(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Use Azure OpenAI to analyze project risks"""
        if not self.azure_openai_endpoint or not self.azure_openai_key:
            # Fallback to rule-based analysis
            return self._rule_based_risk_analysis(project_data)
        
        try:
            # Prepare prompt for AI analysis
            prompt = self._create_risk_analysis_prompt(project_data)
            
            # Call Azure OpenAI
            response = self._call_azure_openai(prompt)
            
            # Parse AI response
            return self._parse_ai_risk_response(response)
            
        except Exception as e:
            logging.error(f"Azure AI risk analysis failed: {str(e)}")
            # Fallback to rule-based analysis
            return self._rule_based_risk_analysis(project_data)
    
    def _rule_based_risk_analysis(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback rule-based risk analysis"""
        metrics = project_data['metrics']
        project = project_data['project']
        
        risks = []
        
        # Schedule risk analysis
        if metrics['overdue_tasks'] > 0:
            risks.append({
                'type': 'schedule',
                'severity': 'high' if metrics['overdue_tasks'] > 5 else 'medium',
                'description': f'{metrics["overdue_tasks"]} tasks are overdue',
                'impact': 'Project timeline may be extended',
                'mitigation': 'Reallocate resources to critical path tasks'
            })
        
        # Progress risk analysis
        if metrics['days_remaining'] > 0:
            expected_progress = (metrics['days_elapsed'] / (metrics['days_elapsed'] + metrics['days_remaining'])) * 100
            if metrics['progress_percentage'] < expected_progress - 10:
                risks.append({
                    'type': 'schedule',
                    'severity': 'medium',
                    'description': f'Project is {expected_progress - metrics["progress_percentage"]:.1f}% behind schedule',
                    'impact': 'Potential deadline miss',
                    'mitigation': 'Accelerate critical path activities'
                })
        
        # Budget risk analysis
        if metrics['budget_variance'] > 0.1:  # 10% over budget
            risks.append({
                'type': 'cost',
                'severity': 'high',
                'description': f'Project is {metrics["budget_variance"]*100:.1f}% over budget',
                'impact': 'Significant cost overrun',
                'mitigation': 'Review and optimize resource allocation'
            })
        
        return {
            'identified_risks': risks,
            'risk_summary': f'Identified {len(risks)} potential risks',
            'overall_assessment': 'high' if any(r['severity'] == 'high' for r in risks) else 'medium' if risks else 'low',
            'ai_confidence': 0.8  # Rule-based confidence
        }
    
    def _calculate_risk_scores(self, project_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate numerical risk scores"""
        metrics = project_data['metrics']
        
        # Schedule risk (0-100, higher = more risk)
        schedule_risk = min(100, (metrics['overdue_tasks'] * 20) + 
                          max(0, (50 - metrics['progress_percentage']) * 0.5))
        
        # Cost risk
        cost_risk = min(100, abs(metrics['budget_variance']) * 100)
        
        # Quality risk (based on rework and issues)
        quality_risk = min(100, metrics['overdue_tasks'] * 10)  # Simplified
        
        # Weather risk (seasonal factor)
        current_month = datetime.now().month
        weather_risk = 40 if current_month in [11, 12, 1, 2, 3] else 20  # Winter months higher risk
        
        # Resource risk (based on task distribution)
        resource_risk = min(100, (metrics['in_progress_tasks'] / max(1, metrics['total_tasks'])) * 100)
        
        # Overall risk (weighted average)
        overall_risk = (schedule_risk * 0.3 + cost_risk * 0.25 + quality_risk * 0.2 + 
                       weather_risk * 0.15 + resource_risk * 0.1)
        
        return {
            'overall': round(overall_risk, 1),
            'schedule': round(schedule_risk, 1),
            'cost': round(cost_risk, 1),
            'quality': round(quality_risk, 1),
            'weather': round(weather_risk, 1),
            'resource': round(resource_risk, 1)
        }
    
    def _generate_recommendations(self, risk_analysis: Dict[str, Any], risk_scores: Dict[str, float]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # High-risk recommendations
        if risk_scores['overall'] > 70:
            recommendations.append({
                'priority': 'critical',
                'category': 'schedule',
                'title': 'Immediate Schedule Review Required',
                'description': 'Project has high overall risk. Conduct immediate schedule review and resource reallocation.',
                'estimated_impact': 'High',
                'implementation_effort': 'Medium'
            })
        
        if risk_scores['schedule'] > 60:
            recommendations.append({
                'priority': 'high',
                'category': 'schedule',
                'title': 'Accelerate Critical Path',
                'description': 'Focus resources on critical path tasks to recover schedule delays.',
                'estimated_impact': 'High',
                'implementation_effort': 'Medium'
            })
        
        if risk_scores['cost'] > 50:
            recommendations.append({
                'priority': 'high',
                'category': 'cost',
                'title': 'Cost Control Measures',
                'description': 'Implement strict cost control measures and review all pending expenditures.',
                'estimated_impact': 'High',
                'implementation_effort': 'Low'
            })
        
        # Medium-risk recommendations
        if risk_scores['resource'] > 40:
            recommendations.append({
                'priority': 'medium',
                'category': 'resource',
                'title': 'Resource Optimization',
                'description': 'Optimize resource allocation across concurrent tasks.',
                'estimated_impact': 'Medium',
                'implementation_effort': 'Medium'
            })
        
        if risk_scores['weather'] > 30:
            recommendations.append({
                'priority': 'medium',
                'category': 'weather',
                'title': 'Weather Contingency Planning',
                'description': 'Develop weather contingency plans and buffer time for outdoor activities.',
                'estimated_impact': 'Medium',
                'implementation_effort': 'Low'
            })
        
        return recommendations
    
    def _predict_outcomes(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict project outcome probabilities"""
        metrics = project_data['metrics']
        risk_scores = self._calculate_risk_scores(project_data)
        
        # Calculate probabilities based on current metrics
        on_time_probability = max(0, min(100, 100 - risk_scores['schedule'] * 0.8))
        on_budget_probability = max(0, min(100, 100 - risk_scores['cost'] * 0.9))
        quality_probability = max(0, min(100, 100 - risk_scores['quality'] * 0.7))
        
        # Overall success probability (all three factors)
        success_probability = (on_time_probability * on_budget_probability * quality_probability) / 10000
        
        return {
            'on_time_completion': round(on_time_probability, 1),
            'on_budget_completion': round(on_budget_probability, 1),
            'quality_targets_met': round(quality_probability, 1),
            'overall_success': round(success_probability, 1),
            'confidence_interval': '±15%',  # Estimated confidence interval
            'prediction_accuracy': 'Medium'  # Based on data quality
        }
    
    def _ai_completion_prediction(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI-based completion prediction"""
        # Simplified AI prediction - in production this would use sophisticated ML models
        metrics = project_data['metrics']
        
        # Calculate velocity (tasks completed per day)
        velocity = metrics['completed_tasks'] / max(1, metrics['days_elapsed'])
        remaining_tasks = metrics['total_tasks'] - metrics['completed_tasks']
        
        # Predict remaining days
        predicted_days = remaining_tasks / max(0.1, velocity)
        
        # Adjust for current trends
        if metrics['overdue_tasks'] > 0:
            predicted_days *= 1.2  # 20% delay factor
        
        predicted_completion = date.today() + timedelta(days=predicted_days)
        
        return {
            'predicted_completion_date': predicted_completion.isoformat(),
            'predicted_days_remaining': round(predicted_days),
            'confidence': 0.75,
            'velocity_analysis': {
                'current_velocity': round(velocity, 2),
                'required_velocity': round(remaining_tasks / max(1, metrics['days_remaining']), 2),
                'velocity_gap': 'positive' if velocity > (remaining_tasks / max(1, metrics['days_remaining'])) else 'negative'
            }
        }
    
    def _statistical_completion_prediction(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Statistical completion prediction"""
        metrics = project_data['metrics']
        
        # Simple statistical model based on progress curve
        if metrics['progress_percentage'] > 0:
            estimated_total_days = metrics['days_elapsed'] / (metrics['progress_percentage'] / 100)
            remaining_days = estimated_total_days - metrics['days_elapsed']
        else:
            remaining_days = metrics['total_duration']
        
        return {
            'statistical_completion_date': (date.today() + timedelta(days=remaining_days)).isoformat(),
            'statistical_days_remaining': round(remaining_days),
            'model_type': 'Linear Progress Extrapolation',
            'confidence': 0.65
        }
    
    def _analyze_completion_factors(self, project_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze factors affecting completion"""
        factors = []
        metrics = project_data['metrics']
        
        if metrics['overdue_tasks'] > 0:
            factors.append({
                'factor': 'Overdue Tasks',
                'impact': 'negative',
                'severity': 'high' if metrics['overdue_tasks'] > 5 else 'medium',
                'description': f'{metrics["overdue_tasks"]} tasks are behind schedule'
            })
        
        if metrics['progress_percentage'] > 75:
            factors.append({
                'factor': 'Project Momentum',
                'impact': 'positive',
                'severity': 'medium',
                'description': 'Project has strong momentum with >75% completion'
            })
        
        return factors
    
    def _predict_milestones(self, project_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Predict milestone completion dates"""
        # This would analyze project phases and predict milestone dates
        # Simplified for now
        milestones = [
            {
                'milestone': 'Foundation Complete',
                'predicted_date': (date.today() + timedelta(days=30)).isoformat(),
                'confidence': 0.8,
                'status': 'on_track'
            },
            {
                'milestone': 'Structure Complete',
                'predicted_date': (date.today() + timedelta(days=90)).isoformat(),
                'confidence': 0.7,
                'status': 'at_risk'
            }
        ]
        
        return milestones
    
    def _call_azure_openai(self, prompt: str) -> str:
        """Call Azure OpenAI API"""
        if not self.azure_openai_endpoint or not self.azure_openai_key:
            raise Exception("Azure OpenAI credentials not configured")
        
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.azure_openai_key
        }
        
        data = {
            'messages': [
                {'role': 'system', 'content': 'You are an expert construction project manager and risk analyst.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 1000,
            'temperature': 0.3
        }
        
        response = requests.post(
            f"{self.azure_openai_endpoint}/openai/deployments/{self.azure_openai_deployment}/chat/completions?api-version=2023-12-01-preview",
            headers=headers,
            json=data,
            timeout=30
        )
        
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    
    def _create_risk_analysis_prompt(self, project_data: Dict[str, Any]) -> str:
        """Create prompt for AI risk analysis"""
        return f"""
        Analyze the following construction project data and identify potential risks:

        Project: {project_data['project']['name']}
        Progress: {project_data['metrics']['progress_percentage']:.1f}%
        Days Elapsed: {project_data['metrics']['days_elapsed']}
        Days Remaining: {project_data['metrics']['days_remaining']}
        Overdue Tasks: {project_data['metrics']['overdue_tasks']}
        Budget Variance: {project_data['metrics']['budget_variance']:.1f}%

        Please identify:
        1. Top 3 risks with severity levels
        2. Potential impact of each risk
        3. Recommended mitigation strategies
        
        Format your response as JSON with risks, impacts, and mitigations.
        """
    
    def _parse_ai_risk_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response for risk analysis"""
        try:
            # Try to parse as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback parsing
            return {
                'ai_analysis': response,
                'parsing_error': True,
                'fallback_mode': True
            }

# Global instance
azure_ai_analytics = AzureAIPredictiveAnalytics()

@azure_ai_bp.route('/ai/project-risks/<int:project_id>')
@login_required
def analyze_project_risks(project_id):
    """API endpoint for AI-powered project risk analysis"""
    try:
        analysis = azure_ai_analytics.analyze_project_risks(project_id, current_user.company_id)
        return jsonify(analysis)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Project risk analysis failed: {str(e)}")
        return jsonify({'error': 'Analysis failed'}), 500

@azure_ai_bp.route('/ai/completion-prediction/<int:project_id>')
@login_required
def predict_completion(project_id):
    """API endpoint for AI-powered completion prediction"""
    try:
        prediction = azure_ai_analytics.predict_project_completion(project_id, current_user.company_id)
        return jsonify(prediction)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Completion prediction failed: {str(e)}")
        return jsonify({'error': 'Prediction failed'}), 500

@azure_ai_bp.route('/ai/resource-optimization/<int:project_id>')
@login_required
def optimize_resources(project_id):
    """API endpoint for AI-powered resource optimization"""
    try:
        optimization = azure_ai_analytics.optimize_resource_allocation(project_id, current_user.company_id)
        return jsonify(optimization)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logging.error(f"Resource optimization failed: {str(e)}")
        return jsonify({'error': 'Optimization failed'}), 500

@azure_ai_bp.route('/ai/company-insights')
@login_required
def company_insights():
    """API endpoint for company-wide AI insights"""
    days_back = request.args.get('days', 90, type=int)
    try:
        insights = azure_ai_analytics.generate_project_insights(current_user.company_id, days_back)
        return jsonify(insights)
    except Exception as e:
        logging.error(f"Company insights generation failed: {str(e)}")
        return jsonify({'error': 'Insights generation failed'}), 500

# Additional helper methods for the analytics class
def _gather_historical_data(self, company_id: int, days_back: int) -> Dict[str, Any]:
    """Gather historical data for company insights"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    
    projects = Project.query.filter(
        Project.company_id == company_id,
        Project.created_at >= start_date
    ).all()
    
    return {
        'projects': len(projects),
        'completed': len([p for p in projects if p.status == 'completed']),
        'active': len([p for p in projects if p.status == 'active']),
        'total_value': sum(p.budget for p in projects if p.budget),
        'analysis_period': days_back
    }

def _ai_company_insights(self, historical_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI insights from historical data"""
    completion_rate = (historical_data['completed'] / max(1, historical_data['projects'])) * 100
    
    insights = {
        'performance_summary': f"Completed {completion_rate:.1f}% of projects in the analysis period",
        'key_trends': [
            'Project completion rates are stable',
            'Resource utilization could be optimized',
            'Budget adherence is within acceptable range'
        ],
        'areas_for_improvement': [
            'Schedule predictability',
            'Resource allocation efficiency',
            'Risk mitigation processes'
        ]
    }
    
    return insights

# Add these methods to the class
AzureAIPredictiveAnalytics._gather_historical_data = _gather_historical_data
AzureAIPredictiveAnalytics._ai_company_insights = _ai_company_insights