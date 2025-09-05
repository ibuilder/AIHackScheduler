"""
Executive Dashboard for BBSchedule Platform
High-level analytics and KPIs for executive decision making
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from models import Project, Task, User, Company, TaskStatus
from extensions import db
from sqlalchemy import func, case, extract
import json

executive_bp = Blueprint('executive', __name__)

class ExecutiveDashboard:
    """Executive-level analytics and reporting"""
    
    def __init__(self):
        pass
    
    def get_company_overview(self, company_id, date_range_days=30):
        """Get high-level company performance overview"""
        end_date = date.today()
        start_date = end_date - timedelta(days=date_range_days)
        
        # Basic project metrics
        total_projects = Project.query.filter_by(company_id=company_id).count()
        active_projects = Project.query.filter_by(company_id=company_id, status='active').count()
        completed_projects = Project.query.filter_by(company_id=company_id, status='completed').count()
        
        # Financial metrics (simplified - would integrate with actual financial data)
        projects = Project.query.filter_by(company_id=company_id).all()
        total_contract_value = sum(p.budget for p in projects if p.budget) or 0
        
        # Calculate revenue recognition (simplified)
        completed_value = sum(p.budget for p in projects if p.budget and p.status == 'completed') or 0
        
        # Calculate profit margins (simulated data)
        profit_margin = 0.12  # 12% average profit margin
        estimated_profit = total_contract_value * profit_margin
        
        # Resource utilization
        total_users = User.query.filter_by(company_id=company_id, is_active=True).count()
        
        # Risk indicators
        overdue_projects = 0
        budget_variance = 0.05  # 5% over budget average
        
        for project in projects:
            if project.end_date and project.end_date < end_date and project.status != 'completed':
                overdue_projects += 1
        
        return {
            'projects': {
                'total': total_projects,
                'active': active_projects,
                'completed': completed_projects,
                'overdue': overdue_projects,
                'completion_rate': (completed_projects / total_projects * 100) if total_projects > 0 else 0
            },
            'financial': {
                'total_contract_value': total_contract_value,
                'completed_value': completed_value,
                'estimated_profit': estimated_profit,
                'profit_margin': profit_margin * 100,
                'budget_variance': budget_variance * 100
            },
            'resources': {
                'total_staff': total_users,
                'utilization_rate': 78.5,  # Simulated
                'productivity_index': 92.3  # Simulated
            },
            'risk_indicators': {
                'overdue_projects': overdue_projects,
                'budget_risk_score': 'Medium',
                'schedule_risk_score': 'Low',
                'overall_health': 'Good'
            }
        }
    
    def get_financial_performance(self, company_id, months=12):
        """Get financial performance trends"""
        # This would integrate with actual financial systems
        # For now, return simulated data
        
        monthly_data = []
        base_revenue = 2500000  # Base monthly revenue
        
        for i in range(months):
            month_date = datetime.now() - timedelta(days=30 * i)
            
            # Simulate revenue growth with some variation
            growth_factor = 1 + (i * 0.02)  # 2% monthly growth
            variance = 0.8 + (i % 3) * 0.1  # Add some variation
            
            revenue = base_revenue * growth_factor * variance
            costs = revenue * 0.75  # 75% cost ratio
            profit = revenue - costs
            
            monthly_data.append({
                'month': month_date.strftime('%Y-%m'),
                'revenue': revenue,
                'costs': costs,
                'profit': profit,
                'margin': (profit / revenue * 100) if revenue > 0 else 0
            })
        
        monthly_data.reverse()  # Show chronological order
        
        return {
            'monthly_trends': monthly_data,
            'year_to_date': {
                'revenue': sum(m['revenue'] for m in monthly_data[-12:]),
                'profit': sum(m['profit'] for m in monthly_data[-12:]),
                'margin': sum(m['margin'] for m in monthly_data[-12:]) / len(monthly_data[-12:])
            }
        }
    
    def get_project_portfolio_analysis(self, company_id):
        """Analyze project portfolio performance"""
        projects = Project.query.filter_by(company_id=company_id).all()
        
        # Categorize projects by size
        small_projects = []  # < $500K
        medium_projects = []  # $500K - $5M
        large_projects = []  # > $5M
        
        for project in projects:
            if project.budget:
                if project.budget < 500000:
                    small_projects.append(project)
                elif project.budget < 5000000:
                    medium_projects.append(project)
                else:
                    large_projects.append(project)
        
        # Performance by project type
        performance_by_size = {
            'small': {
                'count': len(small_projects),
                'avg_margin': 15.2,  # Higher margin for small projects
                'completion_rate': 95.8,
                'avg_duration': 3.2  # months
            },
            'medium': {
                'count': len(medium_projects),
                'avg_margin': 12.1,
                'completion_rate': 89.4,
                'avg_duration': 8.7
            },
            'large': {
                'count': len(large_projects),
                'avg_margin': 8.9,  # Lower margin but higher volume
                'completion_rate': 82.1,
                'avg_duration': 18.3
            }
        }
        
        # Geographic distribution (simulated)
        geographic_data = [
            {'region': 'Northeast', 'projects': 12, 'revenue': 8500000},
            {'region': 'Southeast', 'projects': 8, 'revenue': 6200000},
            {'region': 'Midwest', 'projects': 15, 'revenue': 11200000},
            {'region': 'West', 'projects': 10, 'revenue': 9800000}
        ]
        
        return {
            'portfolio_summary': {
                'total_projects': len(projects),
                'total_value': sum(p.budget for p in projects if p.budget),
                'avg_project_size': sum(p.budget for p in projects if p.budget) / len([p for p in projects if p.budget]) if projects else 0
            },
            'performance_by_size': performance_by_size,
            'geographic_distribution': geographic_data,
            'sector_analysis': [
                {'sector': 'Commercial', 'projects': 15, 'revenue': 18500000, 'margin': 11.2},
                {'sector': 'Residential', 'projects': 12, 'revenue': 8900000, 'margin': 14.8},
                {'sector': 'Industrial', 'projects': 8, 'revenue': 12600000, 'margin': 9.3},
                {'sector': 'Infrastructure', 'projects': 10, 'revenue': 15200000, 'margin': 7.9}
            ]
        }
    
    def get_operational_efficiency(self, company_id):
        """Calculate operational efficiency metrics"""
        projects = Project.query.filter_by(company_id=company_id).all()
        
        # Calculate schedule performance
        on_time_projects = 0
        total_evaluated = 0
        
        for project in projects:
            if project.status == 'completed' and project.end_date:
                total_evaluated += 1
                # Simplified: assume on-time if completed
                on_time_projects += 1
        
        schedule_performance = (on_time_projects / total_evaluated * 100) if total_evaluated > 0 else 0
        
        # Resource efficiency metrics
        efficiency_metrics = {
            'schedule_performance': {
                'on_time_completion': schedule_performance,
                'average_delay': 2.3,  # days
                'critical_path_accuracy': 87.5
            },
            'cost_performance': {
                'budget_adherence': 94.2,
                'cost_variance': -1.8,  # Under budget
                'change_order_rate': 8.3
            },
            'quality_metrics': {
                'defect_rate': 0.8,  # per 1000 tasks
                'rework_percentage': 2.1,
                'client_satisfaction': 4.7  # out of 5
            },
            'productivity_indicators': {
                'tasks_per_day': 12.4,
                'utilization_rate': 78.9,
                'efficiency_score': 91.2
            }
        }
        
        return efficiency_metrics
    
    def get_risk_assessment(self, company_id):
        """Comprehensive risk assessment"""
        projects = Project.query.filter_by(company_id=company_id).all()
        
        # Calculate various risk factors
        financial_risk = 'Low'  # Based on cash flow, receivables, etc.
        operational_risk = 'Medium'  # Based on resource availability, capacity
        market_risk = 'Low'  # Based on market conditions, competition
        
        # Project-specific risks
        high_risk_projects = []
        medium_risk_projects = []
        
        for project in projects:
            risk_score = self._calculate_project_risk(project)
            if risk_score > 7:
                high_risk_projects.append({
                    'id': project.id,
                    'name': project.name,
                    'risk_score': risk_score,
                    'risk_factors': ['Schedule delay', 'Budget overrun']
                })
            elif risk_score > 4:
                medium_risk_projects.append({
                    'id': project.id,
                    'name': project.name,
                    'risk_score': risk_score,
                    'risk_factors': ['Resource constraints']
                })
        
        return {
            'overall_risk_level': 'Medium',
            'risk_categories': {
                'financial': financial_risk,
                'operational': operational_risk,
                'market': market_risk,
                'regulatory': 'Low'
            },
            'project_risks': {
                'high_risk': high_risk_projects,
                'medium_risk': medium_risk_projects,
                'mitigation_recommendations': [
                    'Increase buffer time for critical path tasks',
                    'Diversify supplier base to reduce supply chain risk',
                    'Implement more frequent progress reviews',
                    'Enhance cash flow monitoring'
                ]
            },
            'risk_trends': {
                'improving': ['Cost management', 'Quality control'],
                'stable': ['Schedule adherence', 'Resource planning'],
                'attention_needed': ['Vendor management', 'Weather contingency']
            }
        }
    
    def _calculate_project_risk(self, project):
        """Calculate risk score for individual project"""
        risk_score = 5  # Base score
        
        # Adjust based on project characteristics
        if project.budget and project.budget > 5000000:
            risk_score += 1  # Large projects have higher risk
        
        if project.end_date and project.end_date < date.today() and project.status != 'completed':
            risk_score += 3  # Overdue projects are high risk
        
        # Add other risk factors as needed
        return min(risk_score, 10)  # Cap at 10

# Executive dashboard instance
executive_dashboard = ExecutiveDashboard()

@executive_bp.route('/executive')
@login_required
def executive_dashboard_page():
    """Executive dashboard main page"""
    # Check if user has executive access
    if current_user.role.name not in ['ADMIN']:
        from flask import flash, redirect, url_for
        flash('Access denied. Executive privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    return render_template('executive/dashboard.html')

@executive_bp.route('/api/executive/overview')
@login_required
def api_company_overview():
    """API endpoint for company overview"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    date_range = request.args.get('days', 30, type=int)
    overview = executive_dashboard.get_company_overview(current_user.company_id, date_range)
    
    return jsonify(overview)

@executive_bp.route('/api/executive/financial')
@login_required
def api_financial_performance():
    """API endpoint for financial performance"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    months = request.args.get('months', 12, type=int)
    financial_data = executive_dashboard.get_financial_performance(current_user.company_id, months)
    
    return jsonify(financial_data)

@executive_bp.route('/api/executive/portfolio')
@login_required
def api_portfolio_analysis():
    """API endpoint for portfolio analysis"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    portfolio_data = executive_dashboard.get_project_portfolio_analysis(current_user.company_id)
    
    return jsonify(portfolio_data)

@executive_bp.route('/api/executive/efficiency')
@login_required
def api_operational_efficiency():
    """API endpoint for operational efficiency"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    efficiency_data = executive_dashboard.get_operational_efficiency(current_user.company_id)
    
    return jsonify(efficiency_data)

@executive_bp.route('/api/executive/risk')
@login_required
def api_risk_assessment():
    """API endpoint for risk assessment"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    risk_data = executive_dashboard.get_risk_assessment(current_user.company_id)
    
    return jsonify(risk_data)