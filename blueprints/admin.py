from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import User, Company, Project, Task, AzureIntegration, UserRole
from extensions import db

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            flash('Access denied. Administrator privileges required.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Get company statistics
    total_users = User.query.filter_by(company_id=current_user.company_id).count()
    active_users = User.query.filter_by(
        company_id=current_user.company_id, 
        is_active=True
    ).count()
    
    total_projects = Project.query.filter_by(company_id=current_user.company_id).count()
    active_projects = Project.query.filter_by(
        company_id=current_user.company_id, 
        status='active'
    ).count()
    
    # Get recent activities
    recent_projects = Project.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Project.created_at.desc()).limit(5).all()
    
    recent_users = User.query.filter_by(
        company_id=current_user.company_id
    ).order_by(User.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         active_users=active_users,
                         total_projects=total_projects,
                         active_projects=active_projects,
                         recent_projects=recent_projects,
                         recent_users=recent_users)

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    users = User.query.filter_by(company_id=current_user.company_id).all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        role = request.form.get('role')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('admin/create_user.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('admin/create_user.html')
        
        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            company_id=current_user.company_id,
            role=UserRole(role)
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('User created successfully!', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template('admin/create_user.html')

@admin_bp.route('/integrations')
@login_required
@admin_required
def manage_integrations():
    integrations = AzureIntegration.query.join(Project).filter(
        Project.company_id == current_user.company_id
    ).all()
    
    return render_template('admin/integrations.html', integrations=integrations)

@admin_bp.route('/company/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def company_settings():
    company = Company.query.get(current_user.company_id)
    
    if request.method == 'POST':
        company.name = request.form.get('name')
        company.address = request.form.get('address')
        company.phone = request.form.get('phone')
        company.email = request.form.get('email')
        company.azure_tenant_id = request.form.get('azure_tenant_id')
        company.fabric_workspace_id = request.form.get('fabric_workspace_id')
        
        db.session.commit()
        flash('Company settings updated successfully!', 'success')
        return redirect(url_for('admin.company_settings'))
    
    return render_template('admin/company_settings.html', company=company)

@admin_bp.route('/api/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.company_id != current_user.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'is_active': user.is_active
    })
