"""
Equipment Management Blueprint for BBSchedule Platform
Comprehensive equipment tracking, maintenance, and utilization management
"""

import logging
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from audit.audit_logger import audit_logger
from extensions import db
from models import (
    Equipment,
    EquipmentStatus,
    EquipmentType,
    EquipmentUsageLog,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceType,
    Project,
    Supplier,
    User,
)

equipment_bp = Blueprint("equipment", __name__)


@equipment_bp.route("/equipment")
@login_required
def equipment_list():
    """Display list of all equipment"""
    # Get filter parameters
    equipment_type = request.args.get("type")
    status = request.args.get("status")
    location = request.args.get("location")
    search = request.args.get("search", "").strip()

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
        query = query.filter(Equipment.location.ilike(f"%{location}%"))

    if search:
        query = query.filter(
            or_(
                Equipment.name.ilike(f"%{search}%"),
                Equipment.equipment_number.ilike(f"%{search}%"),
                Equipment.manufacturer.ilike(f"%{search}%"),
                Equipment.model.ilike(f"%{search}%"),
            )
        )

    # Get equipment with pagination
    page = request.args.get("page", 1, type=int)
    equipment_list = query.order_by(Equipment.equipment_number).paginate(
        page=page, per_page=20, error_out=False
    )

    # Get summary statistics
    stats = {
        "total": Equipment.query.filter_by(
            company_id=current_user.company_id, is_active=True
        ).count(),
        "available": Equipment.query.filter_by(
            company_id=current_user.company_id, status=EquipmentStatus.AVAILABLE
        ).count(),
        "in_use": Equipment.query.filter_by(
            company_id=current_user.company_id, status=EquipmentStatus.IN_USE
        ).count(),
        "maintenance": Equipment.query.filter_by(
            company_id=current_user.company_id, status=EquipmentStatus.MAINTENANCE
        ).count(),
        "maintenance_due": Equipment.query.filter(
            Equipment.company_id == current_user.company_id,
            Equipment.next_maintenance_date <= date.today(),
        ).count(),
    }

    return render_template(
        "equipment/list.html",
        equipment_list=equipment_list,
        stats=stats,
        equipment_types=EquipmentType,
        equipment_statuses=EquipmentStatus,
        current_filters={
            "type": equipment_type,
            "status": status,
            "location": location,
            "search": search,
        },
    )


@equipment_bp.route("/equipment/<int:equipment_id>")
@login_required
def equipment_detail(equipment_id):
    """Display detailed equipment information"""
    equipment = Equipment.query.filter_by(
        id=equipment_id, company_id=current_user.company_id
    ).first_or_404()

    recent_maintenance = (
        MaintenanceRecord.query.filter_by(equipment_id=equipment.id)
        .order_by(MaintenanceRecord.scheduled_date.desc())
        .limit(10)
        .all()
    )
    recent_usage = (
        EquipmentUsageLog.query.filter_by(equipment_id=equipment.id)
        .order_by(EquipmentUsageLog.usage_date.desc())
        .limit(30)
        .all()
    )

    ninety_days_ago = date.today() - timedelta(days=90)
    maintenance_cost = sum(
        record.total_cost
        for record in equipment.maintenance_records
        if record.status == MaintenanceStatus.COMPLETED
    )
    usage_stats = {
        "utilization_30d": equipment.utilization_rate(30),
        "utilization_90d": equipment.utilization_rate(90),
        "total_hours_logged": equipment.total_hours_logged,
        "hours_last_90d": sum(
            log.hours_used or 0 for log in recent_usage if log.usage_date >= ninety_days_ago
        ),
        "days_logged": len(recent_usage),
        "maintenance_cost_to_date": float(maintenance_cost),
        "open_maintenance": sum(
            1
            for record in equipment.maintenance_records
            if record.status in (MaintenanceStatus.SCHEDULED, MaintenanceStatus.IN_PROGRESS)
        ),
    }

    return render_template(
        "equipment/detail.html",
        equipment=equipment,
        recent_maintenance=recent_maintenance,
        recent_usage=recent_usage,
        # Inspections have no model yet; an empty list is honest, an invented
        # one is not.
        recent_inspections=[],
        usage_stats=usage_stats,
    )


@equipment_bp.route("/equipment/create", methods=["GET", "POST"])
@login_required
def create_equipment():
    """Create new equipment"""
    if request.method == "POST":
        try:
            # Create new equipment
            equipment = Equipment()
            equipment.equipment_number = request.form.get("equipment_number")
            equipment.name = request.form.get("name")
            equipment.description = request.form.get("description")
            equipment.equipment_type = EquipmentType(request.form.get("equipment_type"))
            equipment.manufacturer = request.form.get("manufacturer")
            equipment.model = request.form.get("model")
            equipment.serial_number = request.form.get("serial_number")
            equipment.year_manufactured = (
                int(request.form.get("year_manufactured"))
                if request.form.get("year_manufactured")
                else None
            )
            equipment.purchase_cost = (
                float(request.form.get("purchase_cost"))
                if request.form.get("purchase_cost")
                else None
            )
            equipment.current_value = (
                float(request.form.get("current_value"))
                if request.form.get("current_value")
                else None
            )
            equipment.location = request.form.get("location")
            equipment.company_id = current_user.company_id

            # Parse purchase date
            purchase_date_str = request.form.get("purchase_date")
            if purchase_date_str:
                equipment.purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").date()

            # Technical specifications
            specs = {}
            if request.form.get("fuel_capacity"):
                specs["fuel_capacity"] = float(request.form.get("fuel_capacity"))
            if request.form.get("max_load_capacity"):
                specs["max_load_capacity"] = float(request.form.get("max_load_capacity"))
            if request.form.get("engine_power"):
                specs["engine_power"] = request.form.get("engine_power")
            if request.form.get("operating_weight"):
                specs["operating_weight"] = float(request.form.get("operating_weight"))

            equipment.specifications = specs if specs else None

            # Maintenance settings
            equipment.maintenance_interval_hours = int(
                request.form.get("maintenance_interval_hours", 250)
            )

            db.session.add(equipment)
            db.session.commit()

            # Log the action
            audit_logger.log_action(
                "equipment_created",
                resource_type="equipment",
                resource_id=equipment.id,
                details={"equipment_number": equipment.equipment_number, "name": equipment.name},
            )

            flash(f'Equipment "{equipment.name}" created successfully!', "success")
            return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating equipment: {str(e)}")
            flash("Error creating equipment. Please try again.", "error")

    # Get suppliers for dropdown
    suppliers = Supplier.query.filter_by(company_id=current_user.company_id, is_active=True).all()

    return render_template(
        "equipment/create.html", equipment_types=EquipmentType, suppliers=suppliers
    )


@equipment_bp.route("/equipment/<int:equipment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_equipment(equipment_id):
    """Edit equipment information"""
    equipment = Equipment.query.filter_by(
        id=equipment_id, company_id=current_user.company_id
    ).first_or_404()

    if request.method == "POST":
        try:
            # Update equipment fields
            equipment.name = request.form.get("name")
            equipment.description = request.form.get("description")
            equipment.location = request.form.get("location")
            try:
                equipment.status = EquipmentStatus(request.form.get("status"))
            except ValueError:
                flash("Invalid status selected.", "error")
                return render_template(
                    "equipment/edit.html", equipment=equipment, equipment_statuses=EquipmentStatus
                )

            # Update technical specifications
            specs = equipment.specifications or {}
            if request.form.get("fuel_capacity"):
                specs["fuel_capacity"] = float(request.form.get("fuel_capacity"))
            if request.form.get("max_load_capacity"):
                specs["max_load_capacity"] = float(request.form.get("max_load_capacity"))

            equipment.specifications = specs
            equipment.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            flash("Equipment updated successfully!", "success")
            return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating equipment: {str(e)}")
            flash("Error updating equipment. Please try again.", "error")

    return render_template(
        "equipment/edit.html", equipment=equipment, equipment_statuses=EquipmentStatus
    )


@equipment_bp.route("/equipment/assign", methods=["POST"])
@login_required
def assign_equipment():
    """Assign equipment to project or user"""
    equipment_id = request.form.get("equipment_id")
    project_id = request.form.get("project_id")
    user_id = request.form.get("user_id")

    equipment = Equipment.query.filter_by(
        id=equipment_id, company_id=current_user.company_id
    ).first_or_404()

    try:
        if project_id:
            project = Project.query.filter_by(
                id=project_id, company_id=current_user.company_id
            ).first()
            if project:
                equipment.current_project_id = project_id
                equipment.status = EquipmentStatus.IN_USE

        if user_id:
            user = User.query.filter_by(id=user_id, company_id=current_user.company_id).first()
            if user:
                equipment.assigned_to_user_id = user_id

        db.session.commit()

        return jsonify({"success": True, "message": "Equipment assigned successfully"})

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error assigning equipment: {str(e)}")
        return jsonify({"success": False, "message": "Assignment failed"}), 500


@equipment_bp.route("/maintenance")
@login_required
def maintenance_schedule():
    """Display maintenance schedule"""
    equipment_list = (
        Equipment.query.filter_by(company_id=current_user.company_id, is_active=True)
        .order_by(Equipment.name)
        .all()
    )

    status_filter = request.args.get("status", "")
    equipment_filter = request.args.get("equipment_id", "")

    records = MaintenanceRecord.query.filter_by(company_id=current_user.company_id)
    if status_filter:
        try:
            records = records.filter_by(status=MaintenanceStatus(status_filter))
        except ValueError:
            flash("Unknown maintenance status filter", "warning")
    if equipment_filter.isdigit():
        records = records.filter_by(equipment_id=int(equipment_filter))

    maintenance_records = records.order_by(MaintenanceRecord.scheduled_date).all()

    today = date.today()
    week_end = today + timedelta(days=7)
    open_statuses = (MaintenanceStatus.SCHEDULED, MaintenanceStatus.IN_PROGRESS)

    stats = {
        "total_scheduled": sum(1 for r in maintenance_records if r.status in open_statuses),
        "overdue": sum(1 for r in maintenance_records if r.is_overdue),
        "this_week": sum(
            1
            for r in maintenance_records
            if r.status in open_statuses and today <= r.scheduled_date <= week_end
        ),
        "total_cost": float(
            sum(
                r.total_cost for r in maintenance_records if r.status == MaintenanceStatus.COMPLETED
            )
        ),
    }

    return render_template(
        "equipment/maintenance_schedule.html",
        maintenance_records=maintenance_records,
        equipment_list=equipment_list,
        stats=stats,
        maintenance_statuses=MaintenanceStatus,
        current_filters={"status": status_filter, "equipment_id": equipment_filter},
    )


@equipment_bp.route("/maintenance/create", methods=["GET", "POST"])
@login_required
def create_maintenance():
    """Create new maintenance record"""
    if request.method == "POST":
        equipment_id = request.form.get("equipment_id", "")
        equipment = Equipment.query.filter_by(
            id=equipment_id if equipment_id.isdigit() else 0,
            company_id=current_user.company_id,
        ).first()

        if equipment is None:
            flash("Select a piece of equipment from your company", "error")
            return redirect(url_for("equipment.create_maintenance"))

        try:
            maintenance_type = MaintenanceType(request.form.get("maintenance_type", ""))
        except ValueError:
            flash("Select a valid maintenance type", "error")
            return redirect(url_for("equipment.create_maintenance"))

        description = (request.form.get("description") or "").strip()
        if not description:
            flash("Describe the work to be done", "error")
            return redirect(url_for("equipment.create_maintenance"))

        try:
            scheduled_date = datetime.strptime(
                request.form.get("scheduled_date", ""), "%Y-%m-%d"
            ).date()
        except ValueError:
            flash("Enter a valid scheduled date", "error")
            return redirect(url_for("equipment.create_maintenance"))

        def _decimal(field):
            raw = request.form.get(field) or "0"
            try:
                return max(0.0, float(raw))
            except ValueError:
                return 0.0

        technician_id = request.form.get("technician_id", "")
        supplier_id = request.form.get("supplier_id", "")

        record = MaintenanceRecord(
            equipment_id=equipment.id,
            maintenance_type=maintenance_type,
            status=MaintenanceStatus.SCHEDULED,
            scheduled_date=scheduled_date,
            description=description,
            labour_cost=_decimal("labour_cost"),
            parts_cost=_decimal("parts_cost"),
            operating_hours_at_service=equipment.operating_hours,
            technician_id=int(technician_id) if technician_id.isdigit() else None,
            supplier_id=int(supplier_id) if supplier_id.isdigit() else None,
            company_id=current_user.company_id,
        )
        db.session.add(record)

        # Keep the machine's own next-service date in step with the schedule.
        if (
            equipment.next_maintenance_date is None
            or scheduled_date < equipment.next_maintenance_date
        ):
            equipment.next_maintenance_date = scheduled_date

        db.session.commit()

        audit_logger.log_action(
            action="maintenance_scheduled",
            resource_type="maintenance_record",
            resource_id=record.id,
            details=f"{maintenance_type.value} on {equipment.name} for {scheduled_date}",
        )
        flash(f"Maintenance scheduled for {equipment.name} on {scheduled_date}", "success")
        return redirect(url_for("equipment.maintenance_schedule"))

    # Get equipment for dropdown
    equipment_list = (
        Equipment.query.filter_by(company_id=current_user.company_id, is_active=True)
        .order_by(Equipment.name)
        .all()
    )

    # Get technicians
    technicians = User.query.filter_by(company_id=current_user.company_id, is_active=True).all()

    # Get suppliers
    suppliers = Supplier.query.filter_by(company_id=current_user.company_id, is_active=True).all()

    return render_template(
        "equipment/create_maintenance.html",
        equipment_list=equipment_list,
        technicians=technicians,
        suppliers=suppliers,
        maintenance_types=MaintenanceType,
    )


@equipment_bp.route("/api/equipment/dashboard-stats")
@login_required
def equipment_dashboard_stats():
    """API endpoint for equipment dashboard statistics"""
    try:
        # Basic counts
        stats = {
            "total_equipment": Equipment.query.filter_by(
                company_id=current_user.company_id, is_active=True
            ).count(),
            "available": Equipment.query.filter_by(
                company_id=current_user.company_id, status=EquipmentStatus.AVAILABLE
            ).count(),
            "in_use": Equipment.query.filter_by(
                company_id=current_user.company_id, status=EquipmentStatus.IN_USE
            ).count(),
            "maintenance": Equipment.query.filter_by(
                company_id=current_user.company_id, status=EquipmentStatus.MAINTENANCE
            ).count(),
            "out_of_service": Equipment.query.filter_by(
                company_id=current_user.company_id, status=EquipmentStatus.OUT_OF_SERVICE
            ).count(),
        }

        # Maintenance due
        maintenance_due = Equipment.query.filter(
            Equipment.company_id == current_user.company_id,
            Equipment.next_maintenance_date <= date.today(),
        ).count()

        stats["maintenance_due"] = maintenance_due

        # Fleet utilisation, measured from logged hours over the last 30 days
        # rather than reported as a constant 78.5 for every company.
        active_equipment = Equipment.query.filter_by(
            company_id=current_user.company_id, is_active=True
        ).all()
        if active_equipment:
            stats["utilization_rate"] = round(
                sum(item.utilization_rate(30) for item in active_equipment) / len(active_equipment),
                1,
            )
        else:
            stats["utilization_rate"] = 0.0
        stats["usage_logged_days"] = (
            db.session.query(func.count(func.distinct(EquipmentUsageLog.usage_date)))
            .filter(
                EquipmentUsageLog.company_id == current_user.company_id,
                EquipmentUsageLog.usage_date >= date.today() - timedelta(days=30),
            )
            .scalar()
            or 0
        )

        # Equipment by type
        equipment_by_type = (
            db.session.query(Equipment.equipment_type, func.count(Equipment.id))
            .filter_by(company_id=current_user.company_id, is_active=True)
            .group_by(Equipment.equipment_type)
            .all()
        )

        stats["by_type"] = {eq_type.value: count for eq_type, count in equipment_by_type}

        return jsonify(stats)

    except Exception as e:
        logging.error(f"Error getting equipment stats: {str(e)}")
        return jsonify({"error": "Failed to load statistics"}), 500


@equipment_bp.route("/api/equipment/utilization-chart")
@login_required
def equipment_utilization_chart():
    """Daily fleet usage over the last 30 days, from recorded usage logs."""
    try:
        window_days = 30
        window_start = date.today() - timedelta(days=window_days - 1)

        rows = (
            db.session.query(
                EquipmentUsageLog.usage_date,
                func.count(func.distinct(EquipmentUsageLog.equipment_id)),
                func.coalesce(func.sum(EquipmentUsageLog.hours_used), 0),
            )
            .filter(
                EquipmentUsageLog.company_id == current_user.company_id,
                EquipmentUsageLog.usage_date >= window_start,
            )
            .group_by(EquipmentUsageLog.usage_date)
            .all()
        )
        by_date = {row[0]: (row[1], float(row[2])) for row in rows}

        # Days with no logged usage are genuine zeroes, not gaps to interpolate.
        days = [window_start + timedelta(days=offset) for offset in range(window_days)]
        chart_data = {
            "labels": [day.strftime("%m/%d") for day in days],
            "equipment_used": [by_date.get(day, (0, 0.0))[0] for day in days],
            "total_hours": [by_date.get(day, (0, 0.0))[1] for day in days],
            "has_data": bool(by_date),
        }

        return jsonify(chart_data)

    except Exception as e:
        logging.error(f"Error getting utilization chart data: {str(e)}")
        return jsonify({"error": "Failed to load chart data"}), 500


@equipment_bp.route("/equipment/<int:equipment_id>/usage", methods=["POST"])
@login_required
def log_equipment_usage(equipment_id):
    """Record hours worked, which is what utilisation is computed from."""
    equipment = Equipment.query.filter_by(
        id=equipment_id, company_id=current_user.company_id
    ).first_or_404()

    try:
        usage_date = datetime.strptime(request.form.get("usage_date", ""), "%Y-%m-%d").date()
    except ValueError:
        flash("Enter a valid usage date", "error")
        return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))

    if usage_date > date.today():
        flash("Usage cannot be recorded for a future date", "error")
        return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))

    try:
        hours = float(request.form.get("hours_used", "0"))
    except ValueError:
        hours = -1
    if not 0 <= hours <= 24:
        flash("Hours used must be between 0 and 24", "error")
        return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))

    project_id = request.form.get("project_id", "")
    project = None
    if project_id.isdigit():
        project = Project.query.filter_by(
            id=int(project_id), company_id=current_user.company_id
        ).first()

    # One row per machine per day, so a correction updates rather than doubles.
    existing = EquipmentUsageLog.query.filter_by(
        equipment_id=equipment.id, usage_date=usage_date
    ).first()

    previous_hours = existing.hours_used if existing else 0.0
    if existing:
        existing.hours_used = hours
        existing.project_id = project.id if project else None
        existing.notes = (request.form.get("notes") or "")[:2000] or None
        log = existing
    else:
        log = EquipmentUsageLog(
            equipment_id=equipment.id,
            usage_date=usage_date,
            hours_used=hours,
            project_id=project.id if project else None,
            operator_id=current_user.id,
            notes=(request.form.get("notes") or "")[:2000] or None,
            company_id=current_user.company_id,
        )
        db.session.add(log)

    # The lifetime meter follows the logs, which is what drives interval-based
    # maintenance scheduling.
    equipment.operating_hours = (equipment.operating_hours or 0) - previous_hours + hours
    db.session.commit()

    audit_logger.log_action(
        action="equipment_usage_logged",
        resource_type="equipment",
        resource_id=equipment.id,
        details=f"{hours}h on {usage_date}",
    )
    flash(f"Logged {hours} hours for {equipment.name} on {usage_date}", "success")
    return redirect(url_for("equipment.equipment_detail", equipment_id=equipment.id))
