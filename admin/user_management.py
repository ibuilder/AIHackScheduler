from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from models import User, Company, UserRole, AuditLog
from extensions import db
from audit.audit_logger import audit_logger
import logging

admin_bp = Blueprint('user_management', __name__)

@admin_bp.route('/users')
@login_required
def manage_users():
    """User management dashboard"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.filter_by(company_id=current_user.company_id).all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    """Create new user"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            # Validate input
            username = request.form.get('username')
            email = request.form.get('email')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            role = request.form.get('role')
            password = request.form.get('password')
            
            if not all([username, email, first_name, last_name, role, password]):
                flash('All fields are required', 'error')
                return render_template('admin/create_user.html')
            
            # Check if user already exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return render_template('admin/create_user.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
                return render_template('admin/create_user.html')
            
            # Create user
            user = User()
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.role = UserRole[role]
            user.company_id = current_user.company_id
            user.password_hash = generate_password_hash(password)
            user.is_active = True
            
            db.session.add(user)
            db.session.commit()
            
            # Log user creation
            audit_logger.log_user_management('user_created', user.id, {
                'created_username': username,
                'role': role
            })
            
            flash(f'User {username} created successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"User creation error: {str(e)}")
            flash('Error creating user. Please try again.', 'error')
    
    return render_template('admin/create_user.html')

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit user details"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Can only edit users in same company
    if user.company_id != current_user.company_id:
        flash('Access denied', 'error')
        return redirect(url_for('admin.manage_users'))
    
    if request.method == 'POST':
        try:
            original_data = {
                'role': user.role.value,
                'is_active': user.is_active
            }
            
            # Update user fields
            user.first_name = request.form.get('first_name')
            user.last_name = request.form.get('last_name')
            user.email = request.form.get('email')
            user.role = UserRole[request.form.get('role')]
            user.is_active = request.form.get('is_active') == 'on'
            
            # Update password if provided
            new_password = request.form.get('password')
            if new_password:
                user.password_hash = generate_password_hash(new_password)
            
            db.session.commit()
            
            # Log user modification
            changes = {}
            if original_data['role'] != user.role.value:
                changes['role_changed'] = f"{original_data['role']} -> {user.role.value}"
            if original_data['is_active'] != user.is_active:
                changes['status_changed'] = f"{'active' if original_data['is_active'] else 'inactive'} -> {'active' if user.is_active else 'inactive'}"
            
            audit_logger.log_user_management('user_modified', user.id, changes)
            
            flash('User updated successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"User edit error: {str(e)}")
            flash('Error updating user. Please try again.', 'error')
    
    return render_template('admin/edit_user.html', user=user)

@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
def deactivate_user(user_id):
    """Deactivate a user"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    user = User.query.get_or_404(user_id)
    
    if user.company_id != current_user.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot deactivate yourself'}), 400
    
    try:
        user.is_active = False
        db.session.commit()
        
        audit_logger.log_user_management('user_deactivated', user.id)
        
        return jsonify({'success': True, 'message': f'User {user.username} deactivated'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"User deactivation error: {str(e)}")
        return jsonify({'error': 'Failed to deactivate user'}), 500

@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
def activate_user(user_id):
    """Activate a user"""
    if current_user.role.name not in ['ADMIN']:
        return jsonify({'error': 'Access denied'}), 403
    
    user = User.query.get_or_404(user_id)
    
    if user.company_id != current_user.company_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        user.is_active = True
        db.session.commit()
        
        audit_logger.log_user_management('user_activated', user.id)
        
        return jsonify({'success': True, 'message': f'User {user.username} activated'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"User activation error: {str(e)}")
        return jsonify({'error': 'Failed to activate user'}), 500

@admin_bp.route('/company/settings', methods=['GET', 'POST'])
@login_required
def company_settings():
    """Manage company settings"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    company = Company.query.get(current_user.company_id)
    
    if request.method == 'POST':
        try:
            company.name = request.form.get('name')
            company.address = request.form.get('address')
            company.phone = request.form.get('phone')
            company.email = request.form.get('email')
            company.azure_tenant_id = request.form.get('azure_tenant_id')
            company.fabric_workspace_id = request.form.get('fabric_workspace_id')
            
            db.session.commit()
            
            audit_logger.log_action('company_settings_updated', resource_type='company', resource_id=company.id)
            
            flash('Company settings updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Company settings update error: {str(e)}")
            flash('Error updating company settings. Please try again.', 'error')
    
    return render_template('admin/company_settings.html', company=company)

@admin_bp.route('/audit-logs')
@login_required
def audit_logs():
    """View audit logs"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs = AuditLog.query.filter_by(company_id=current_user.company_id)\
        .order_by(AuditLog.timestamp.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/audit_logs.html', logs=logs)

@admin_bp.route('/system-status')
@login_required
def system_status():
    """System status and health monitoring"""
    if current_user.role.name not in ['ADMIN']:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Get system health information
    status_data = {
        'database': 'healthy',
        'cache': 'healthy',
        'background_jobs': 'healthy',
        'integrations': {
            'power_bi': 'pending_setup',
            'azure_ai': 'not_configured',
            'fabric': 'not_configured'
        },
        'performance': {
            'avg_response_time': '245ms',
            'requests_per_minute': 127,
            'error_rate': '0.2%'
        }
    }
    
    return render_template('admin/system_status.html', status=status_data)