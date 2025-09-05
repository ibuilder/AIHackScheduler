"""
Equipment Management Blueprint for BBSchedule Platform
Comprehensive equipment tracking, maintenance, and utilization management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta, timezone
from models import Equipment, Supplier, EquipmentType, EquipmentStatus, MaintenanceType, MaintenanceStatus
from models import Project, Task, User
from extensions import db
from audit.audit_logger import audit_logger
import json
import logging
from sqlalchemy import func, and_, or_

equipment_bp = Blueprint('equipment', __name__)

@equipment_bp.route('/equipment')
@login_required
def equipment_list():
    """Display list of all equipment"""
    # Get filter parameters
    equipment_type = request.args.get('type')
    status = request.args.get('status')
    location = request.args.get('location')
    search = request.args.get('search', '').strip()
    
    # Base query
    query = Equipment.query.filter_by(company_id=current_user.company_id, is_active=True)
    
    # Apply filters with proper enum handling
    if equipment_type:
        try:
            equipment_type_enum = EquipmentType(equipment_type)
            query = query.filter(Equipment.equipment_type == equipment_type_enum)
        except ValueError:
            pass  # Invalid enum value, ignore filter
    
    if status:
        try:
            status_enum = EquipmentStatus(status)
            query = query.filter(Equipment.status == status_enum)
        except ValueError:
            pass  # Invalid enum value, ignore filter
    
    if location:
        query = query.filter(Equipment.location.ilike(f'%{location}%'))
    
    if search:
        query = query.filter(
            or_(
                Equipment.name.ilike(f'%{search}%'),
                Equipment.equipment_number.ilike(f'%{search}%'),
                Equipment.manufacturer.ilike(f'%{search}%'),
                Equipment.model.ilike(f'%{search}%')
            )
        )
    
    # Get equipment with pagination
    page = request.args.get('page', 1, type=int)
    equipment_list = query.order_by(Equipment.equipment_number).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get summary statistics
    stats = {
        'total': Equipment.query.filter_by(company_id=current_user.company_id, is_active=True).count(),
        'available': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.AVAILABLE).count(),
        'in_use': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.IN_USE).count(),
        'maintenance': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.MAINTENANCE).count(),
        'maintenance_due': Equipment.query.filter(
            Equipment.company_id == current_user.company_id,
            Equipment.next_maintenance_date <= date.today()
        ).count()
    }
    
    return render_template('equipment/list.html', 
                         equipment_list=equipment_list,
                         stats=stats,
                         equipment_types=EquipmentType,
                         equipment_statuses=EquipmentStatus,
                         current_filters={
                             'type': equipment_type,
                             'status': status,
                             'location': location,
                             'search': search
                         })

@equipment_bp.route('/equipment/<int:equipment_id>')
@login_required
def equipment_detail(equipment_id):
    """Display detailed equipment information"""
    equipment = Equipment.query.filter_by(
        id=equipment_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    # Placeholder for maintenance, usage, and inspection data
    # These would be implemented with proper models
    recent_maintenance = []
    recent_usage = []
    recent_inspections = []
    usage_stats = None
    
    return render_template('equipment/detail.html',
                         equipment=equipment,
                         recent_maintenance=recent_maintenance,
                         recent_usage=recent_usage,
                         recent_inspections=recent_inspections,
                         usage_stats=usage_stats)

@equipment_bp.route('/equipment/create', methods=['GET', 'POST'])
@login_required
def create_equipment():
    """Create new equipment"""
    if request.method == 'POST':
        try:
            # Create new equipment
            equipment = Equipment()
            equipment.equipment_number = request.form.get('equipment_number')
            equipment.name = request.form.get('name')
            equipment.description = request.form.get('description')
            equipment.equipment_type = EquipmentType(request.form.get('equipment_type'))
            equipment.manufacturer = request.form.get('manufacturer')
            equipment.model = request.form.get('model')
            equipment.serial_number = request.form.get('serial_number')
            equipment.year_manufactured = int(request.form.get('year_manufactured')) if request.form.get('year_manufactured') else None
            equipment.purchase_cost = float(request.form.get('purchase_cost')) if request.form.get('purchase_cost') else None
            equipment.current_value = float(request.form.get('current_value')) if request.form.get('current_value') else None
            equipment.location = request.form.get('location')
            equipment.company_id = current_user.company_id
            
            # Parse purchase date
            purchase_date_str = request.form.get('purchase_date')
            if purchase_date_str:
                equipment.purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
            
            # Technical specifications
            specs = {}
            if request.form.get('fuel_capacity'):
                specs['fuel_capacity'] = float(request.form.get('fuel_capacity'))
            if request.form.get('max_load_capacity'):
                specs['max_load_capacity'] = float(request.form.get('max_load_capacity'))
            if request.form.get('engine_power'):
                specs['engine_power'] = request.form.get('engine_power')
            if request.form.get('operating_weight'):
                specs['operating_weight'] = float(request.form.get('operating_weight'))
            
            equipment.specifications = specs if specs else None
            
            # Maintenance settings
            equipment.maintenance_interval_hours = int(request.form.get('maintenance_interval_hours', 250))
            
            db.session.add(equipment)
            db.session.commit()
            
            # Log the action
            audit_logger.log_action(
                'equipment_created',
                resource_type='equipment',
                resource_id=equipment.id,
                details={'equipment_number': equipment.equipment_number, 'name': equipment.name}
            )
            
            flash(f'Equipment "{equipment.name}" created successfully!', 'success')
            return redirect(url_for('equipment.equipment_detail', equipment_id=equipment.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating equipment: {str(e)}")
            flash('Error creating equipment. Please try again.', 'error')
    
    # Get suppliers for dropdown
    suppliers = Supplier.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    return render_template('equipment/create.html',
                         equipment_types=EquipmentType,
                         suppliers=suppliers)

@equipment_bp.route('/equipment/<int:equipment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_equipment(equipment_id):
    """Edit equipment information"""
    equipment = Equipment.query.filter_by(
        id=equipment_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    if request.method == 'POST':
        try:
            # Update equipment fields
            equipment.name = request.form.get('name')
            equipment.description = request.form.get('description')
            equipment.location = request.form.get('location')
            try:
                equipment.status = EquipmentStatus(request.form.get('status'))
            except ValueError:
                flash('Invalid status selected.', 'error')
                return render_template('equipment/edit.html', equipment=equipment, equipment_statuses=EquipmentStatus)
            
            # Update technical specifications
            specs = equipment.specifications or {}
            if request.form.get('fuel_capacity'):
                specs['fuel_capacity'] = float(request.form.get('fuel_capacity'))
            if request.form.get('max_load_capacity'):
                specs['max_load_capacity'] = float(request.form.get('max_load_capacity'))
            
            equipment.specifications = specs
            equipment.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            flash('Equipment updated successfully!', 'success')
            return redirect(url_for('equipment.equipment_detail', equipment_id=equipment.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating equipment: {str(e)}")
            flash('Error updating equipment. Please try again.', 'error')
    
    return render_template('equipment/edit.html',
                         equipment=equipment,
                         equipment_statuses=EquipmentStatus)

@equipment_bp.route('/equipment/assign', methods=['POST'])
@login_required
def assign_equipment():
    """Assign equipment to project or user"""
    equipment_id = request.form.get('equipment_id')
    project_id = request.form.get('project_id')
    user_id = request.form.get('user_id')
    
    equipment = Equipment.query.filter_by(
        id=equipment_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    try:
        if project_id:
            project = Project.query.filter_by(id=project_id, company_id=current_user.company_id).first()
            if project:
                equipment.current_project_id = project_id
                equipment.status = EquipmentStatus.IN_USE
        
        if user_id:
            user = User.query.filter_by(id=user_id, company_id=current_user.company_id).first()
            if user:
                equipment.assigned_to_user_id = user_id
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Equipment assigned successfully'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error assigning equipment: {str(e)}")
        return jsonify({'success': False, 'message': 'Assignment failed'}), 500

@equipment_bp.route('/maintenance')
@login_required
def maintenance_schedule():
    """Display maintenance schedule"""
    # Placeholder maintenance schedule - would implement with proper models
    equipment_list = Equipment.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).order_by(Equipment.name).all()
    
    # Calculate basic statistics
    stats = {
        'total_scheduled': 0,
        'overdue': 0,
        'this_week': 0,
        'total_cost': 0
    }
    
    return render_template('equipment/maintenance_schedule.html',
                         maintenance_records=[],
                         equipment_list=equipment_list,
                         stats=stats,
                         maintenance_statuses=MaintenanceStatus,
                         current_filters={})

@equipment_bp.route('/maintenance/create', methods=['GET', 'POST'])
@login_required
def create_maintenance():
    """Create new maintenance record"""
    if request.method == 'POST':
        # Placeholder - would implement with proper MaintenanceRecord model
        flash('Maintenance scheduling feature coming soon!', 'info')
        return redirect(url_for('equipment.maintenance_schedule'))
    
    # Get equipment for dropdown
    equipment_list = Equipment.query.filter_by(
        company_id=current_user.company_id,
        is_active=True
    ).order_by(Equipment.name).all()
    
    # Get technicians
    technicians = User.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    # Get suppliers
    suppliers = Supplier.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    return render_template('equipment/create_maintenance.html',
                         equipment_list=equipment_list,
                         technicians=technicians,
                         suppliers=suppliers,
                         maintenance_types=MaintenanceType)

@equipment_bp.route('/api/equipment/dashboard-stats')
@login_required
def equipment_dashboard_stats():
    """API endpoint for equipment dashboard statistics"""
    try:
        # Basic counts
        stats = {
            'total_equipment': Equipment.query.filter_by(company_id=current_user.company_id, is_active=True).count(),
            'available': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.AVAILABLE).count(),
            'in_use': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.IN_USE).count(),
            'maintenance': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.MAINTENANCE).count(),
            'out_of_service': Equipment.query.filter_by(company_id=current_user.company_id, status=EquipmentStatus.OUT_OF_SERVICE).count()
        }
        
        # Maintenance due
        maintenance_due = Equipment.query.filter(
            Equipment.company_id == current_user.company_id,
            Equipment.next_maintenance_date <= date.today()
        ).count()
        
        stats['maintenance_due'] = maintenance_due
        
        # Placeholder utilization rate
        stats['utilization_rate'] = 78.5
        
        # Equipment by type
        equipment_by_type = db.session.query(
            Equipment.equipment_type,
            func.count(Equipment.id)
        ).filter_by(company_id=current_user.company_id, is_active=True).group_by(Equipment.equipment_type).all()
        
        stats['by_type'] = {eq_type.value: count for eq_type, count in equipment_by_type}
        
        return jsonify(stats)
        
    except Exception as e:
        logging.error(f"Error getting equipment stats: {str(e)}")
        return jsonify({'error': 'Failed to load statistics'}), 500

@equipment_bp.route('/api/equipment/utilization-chart')
@login_required
def equipment_utilization_chart():
    """API endpoint for equipment utilization chart data"""
    try:
        # Placeholder chart data
        thirty_days_ago = date.today() - timedelta(days=30)
        chart_data = {
            'labels': [(thirty_days_ago + timedelta(days=i)).strftime('%m/%d') for i in range(30)],
            'equipment_used': [5, 7, 6, 8, 9, 7, 8, 6, 9, 10, 8, 7, 9, 8, 10, 9, 8, 7, 6, 8, 9, 7, 8, 10, 9, 8, 7, 6, 8, 9],
            'total_hours': [40, 56, 48, 64, 72, 56, 64, 48, 72, 80, 64, 56, 72, 64, 80, 72, 64, 56, 48, 64, 72, 56, 64, 80, 72, 64, 56, 48, 64, 72]
        }
        
        return jsonify(chart_data)
        
    except Exception as e:
        logging.error(f"Error getting utilization chart data: {str(e)}")
        return jsonify({'error': 'Failed to load chart data'}), 500