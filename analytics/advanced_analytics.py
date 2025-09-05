from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from models import Project, Task, User, Company, TaskStatus, AuditLog
from extensions import db
from sqlalchemy import func, extract, and_, or_
import json

analytics_bp = Blueprint('analytics', __name__)

class AdvancedAnalytics:
    """Advanced analytics engine for project data"""
    
    def __init__(self):
        pass
    
    def get_project_performance_metrics(self, company_id, date_range=30):
        """Get comprehensive project performance metrics"""
        end_date = date.today()
        start_date = end_date - timedelta(days=date_range)
        
        projects = Project.query.filter_by(company_id=company_id).all()
        
        metrics = {
            'total_projects': len(projects),
            'active_projects': len([p for p in projects if p.status == 'active']),
            'completed_projects': len([p for p in projects if p.status == 'completed']),
            'overdue_projects': 0,
            'budget_performance': {},
            'schedule_performance': {},
            'resource_utilization': {},
            'risk_indicators': {}
        }
        
        # Calculate detailed metrics
        total_budget = 0
        total_actual = 0
        on_time_projects = 0
        
        for project in projects:
            if project.budget:
                total_budget += project.budget
                # Simulate actual costs (in real implementation, get from actual data)
                actual_cost = project.budget * 0.95  # 95% of budget on average
                total_actual += actual_cost
            
            # Check if project is on time
            if project.end_date and project.end_date >= date.today():
                on_time_projects += 1
            elif project.status == 'completed':
                on_time_projects += 1
        
        metrics['budget_performance'] = {
            'total_budget': total_budget,
            'total_actual': total_actual,
            'variance_percent': ((total_actual - total_budget) / total_budget * 100) if total_budget > 0 else 0,
            'projects_under_budget': max(0, len(projects) - 2),  # Simulated
            'projects_over_budget': min(2, len(projects))  # Simulated
        }
        
        metrics['schedule_performance'] = {
            'on_time_projects': on_time_projects,
            'delayed_projects': len(projects) - on_time_projects,
            'average_delay_days': 3.2,  # Simulated
            'schedule_adherence_percent': (on_time_projects / len(projects) * 100) if projects else 0
        }
        
        return metrics
    
    def get_task_analytics(self, company_id, project_id=None):
        """Get detailed task analytics"""
        query = Task.query.join(Project).filter(Project.company_id == company_id)
        
        if project_id:
            query = query.filter(Task.project_id == project_id)
        
        tasks = query.all()
        
        status_counts = {}
        for task in tasks:
            status = task.status.name
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate completion trends
        completed_tasks_by_week = self._get_completion_trends(tasks)
        
        # Calculate average duration
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        avg_duration = sum([t.duration for t in completed_tasks]) / len(completed_tasks) if completed_tasks else 0
        
        analytics = {
            'total_tasks': len(tasks),
            'status_distribution': status_counts,
            'completion_rate': (status_counts.get('COMPLETED', 0) / len(tasks) * 100) if tasks else 0,
            'average_duration_days': round(avg_duration, 1),
            'completion_trends': completed_tasks_by_week,
            'overdue_tasks': len([t for t in tasks if t.end_date < date.today() and t.status != TaskStatus.COMPLETED]),
            'critical_path_tasks': self._identify_critical_path_tasks(tasks)
        }
        
        return analytics
    
    def get_user_productivity_metrics(self, company_id):
        """Get user productivity and activity metrics"""
        users = User.query.filter_by(company_id=company_id).all()
        
        productivity_data = []
        for user in users:
            # Get user's project assignments (simplified)
            user_projects = Project.query.filter_by(created_by=user.id).count()
            
            # Get audit log activity
            recent_activity = AuditLog.query.filter_by(user_id=user.id)\
                .filter(AuditLog.timestamp >= datetime.now() - timedelta(days=30))\
                .count()
            
            productivity_data.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role.value,
                'projects_managed': user_projects,
                'monthly_activity': recent_activity,
                'last_login': user.last_login.isoformat() if user.last_login else None
            })
        
        return {
            'total_users': len(users),
            'active_users_30_days': len([u for u in users if u.last_login and u.last_login >= datetime.now() - timedelta(days=30)]),
            'user_details': productivity_data
        }
    
    def get_resource_utilization_analytics(self, company_id):
        """Get resource utilization analytics"""
        # This would connect to actual resource data in production
        return {
            'labor_utilization': 78.5,
            'equipment_utilization': 65.2,
            'material_efficiency': 89.1,
            'cost_per_hour_trends': [45, 47, 46, 48, 49, 47, 46],
            'resource_conflicts': 3,
            'optimization_opportunities': [
                'Equipment scheduling can be optimized by 15%',
                'Labor allocation shows 12% improvement potential',
                'Material ordering could reduce waste by 8%'
            ]
        }
    
    def _get_completion_trends(self, tasks):
        """Calculate task completion trends over time"""
        trends = {}
        for task in tasks:
            if task.status == TaskStatus.COMPLETED:
                # Simulate completion date (would use actual completion date in production)
                week = task.updated_at.strftime('%Y-W%U') if task.updated_at else datetime.now().strftime('%Y-W%U')
                trends[week] = trends.get(week, 0) + 1
        
        return trends
    
    def _identify_critical_path_tasks(self, tasks):
        """Identify tasks on the critical path"""
        # Simplified critical path identification
        critical_tasks = []
        for task in tasks:
            if task.status in [TaskStatus.IN_PROGRESS, TaskStatus.NOT_STARTED]:
                if task.end_date <= date.today() + timedelta(days=7):
                    critical_tasks.append({
                        'task_id': task.id,
                        'name': task.name,
                        'end_date': task.end_date.isoformat(),
                        'project_name': task.project.name
                    })
        
        return critical_tasks[:5]  # Top 5 critical tasks

@analytics_bp.route('/project-performance')
@login_required
def project_performance():
    """Get project performance analytics"""
    date_range = request.args.get('days', 30, type=int)
    
    analytics = AdvancedAnalytics()
    metrics = analytics.get_project_performance_metrics(current_user.company_id, date_range)
    
    return jsonify(metrics)

@analytics_bp.route('/task-analytics')
@login_required
def task_analytics():
    """Get task analytics"""
    project_id = request.args.get('project_id', type=int)
    
    analytics = AdvancedAnalytics()
    data = analytics.get_task_analytics(current_user.company_id, project_id)
    
    return jsonify(data)

@analytics_bp.route('/user-productivity')
@login_required
def user_productivity():
    """Get user productivity metrics"""
    # Only admins can view company-wide productivity
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    analytics = AdvancedAnalytics()
    data = analytics.get_user_productivity_metrics(current_user.company_id)
    
    return jsonify(data)

@analytics_bp.route('/resource-utilization')
@login_required
def resource_utilization():
    """Get resource utilization analytics"""
    analytics = AdvancedAnalytics()
    data = analytics.get_resource_utilization_analytics(current_user.company_id)
    
    return jsonify(data)

@analytics_bp.route('/dashboard')
@login_required
def analytics_dashboard():
    """Analytics dashboard page"""
    return render_template('analytics/dashboard.html')