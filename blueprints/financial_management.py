"""
Financial Management Blueprint for BBSchedule Platform
Comprehensive financial tracking, invoicing, and payment management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from models import (
    Transaction, ProjectBudget, Invoice, InvoiceItem, Payment,
    TransactionType, PaymentMethod, PaymentStatus, InvoiceStatus, 
    ExpenseCategory, BudgetCategory, Project, Task, User
)
from extensions import db
from audit.audit_logger import audit_logger
import logging
from sqlalchemy import func, and_, or_, extract
import os

financial_bp = Blueprint('financial', __name__)

@financial_bp.route('/financial')
@login_required
def financial_dashboard():
    """Display financial dashboard with key metrics"""
    # Get current month/year for filtering
    current_month = date.today().month
    current_year = date.today().year
    
    # Calculate financial metrics
    stats = {
        'total_revenue': get_total_revenue(current_user.company_id, current_year),
        'total_expenses': get_total_expenses(current_user.company_id, current_year),
        'outstanding_invoices': get_outstanding_invoices(current_user.company_id),
        'cash_flow': get_cash_flow(current_user.company_id, current_month, current_year)
    }
    
    # Get recent transactions
    recent_transactions = Transaction.query.filter_by(
        company_id=current_user.company_id
    ).order_by(Transaction.transaction_date.desc()).limit(10).all()
    
    # Get overdue invoices
    overdue_invoices = Invoice.query.filter(
        Invoice.company_id == current_user.company_id,
        Invoice.due_date < date.today(),
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL])
    ).order_by(Invoice.due_date).all()
    
    return render_template('financial/dashboard.html',
                         stats=stats,
                         recent_transactions=recent_transactions,
                         overdue_invoices=overdue_invoices)

@financial_bp.route('/transactions')
@login_required
def transaction_list():
    """Display list of all transactions"""
    # Get filter parameters
    transaction_type = request.args.get('type')
    category = request.args.get('category')
    project_id = request.args.get('project')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Base query
    query = Transaction.query.filter_by(company_id=current_user.company_id)
    
    # Apply filters
    if transaction_type:
        try:
            type_enum = TransactionType(transaction_type)
            query = query.filter(Transaction.transaction_type == type_enum)
        except ValueError:
            pass
    
    if category:
        try:
            category_enum = ExpenseCategory(category)
            query = query.filter(Transaction.expense_category == category_enum)
        except ValueError:
            pass
    
    if project_id:
        query = query.filter(Transaction.project_id == project_id)
    
    if date_from:
        query = query.filter(Transaction.transaction_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    
    if date_to:
        query = query.filter(Transaction.transaction_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    # Get transactions with pagination
    page = request.args.get('page', 1, type=int)
    transactions = query.order_by(Transaction.transaction_date.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    
    # Get projects for filter dropdown
    projects = Project.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    return render_template('financial/transactions.html',
                         transactions=transactions,
                         projects=projects,
                         transaction_types=TransactionType,
                         expense_categories=ExpenseCategory,
                         current_filters={
                             'type': transaction_type,
                             'category': category,
                             'project': project_id,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@financial_bp.route('/transactions/create', methods=['GET', 'POST'])
@login_required
def create_transaction():
    """Create new financial transaction"""
    if request.method == 'POST':
        try:
            # Generate transaction number
            transaction_number = generate_transaction_number(current_user.company_id)
            
            transaction = Transaction()
            transaction.transaction_number = transaction_number
            transaction.transaction_type = TransactionType(request.form.get('transaction_type'))
            transaction.amount = Decimal(request.form.get('amount'))
            transaction.description = request.form.get('description')
            transaction.transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date()
            transaction.company_id = current_user.company_id
            transaction.created_by_id = current_user.id
            
            # Optional fields
            if request.form.get('expense_category'):
                transaction.expense_category = ExpenseCategory(request.form.get('expense_category'))
            
            if request.form.get('project_id'):
                transaction.project_id = int(request.form.get('project_id'))
            
            if request.form.get('task_id'):
                transaction.task_id = int(request.form.get('task_id'))
            
            if request.form.get('equipment_id'):
                transaction.equipment_id = int(request.form.get('equipment_id'))
            
            if request.form.get('payment_method'):
                transaction.payment_method = PaymentMethod(request.form.get('payment_method'))
            
            transaction.payment_reference = request.form.get('payment_reference')
            transaction.vendor_customer_name = request.form.get('vendor_customer_name')
            transaction.reference_number = request.form.get('reference_number')
            
            db.session.add(transaction)
            db.session.commit()
            
            # Log the action
            audit_logger.log_action(
                'transaction_created',
                resource_type='transaction',
                resource_id=transaction.id,
                details={'transaction_number': transaction.transaction_number, 'amount': str(transaction.amount)}
            )
            
            flash(f'Transaction {transaction.transaction_number} created successfully!', 'success')
            return redirect(url_for('financial.transaction_list'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating transaction: {str(e)}")
            flash('Error creating transaction. Please try again.', 'error')
    
    # Get data for form dropdowns
    projects = Project.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    return render_template('financial/create_transaction.html',
                         projects=projects,
                         transaction_types=TransactionType,
                         expense_categories=ExpenseCategory,
                         payment_methods=PaymentMethod)

@financial_bp.route('/invoices')
@login_required
def invoice_list():
    """Display list of all invoices"""
    # Get filter parameters
    status_filter = request.args.get('status')
    project_filter = request.args.get('project')
    overdue_only = request.args.get('overdue') == 'true'
    
    # Base query
    query = Invoice.query.filter_by(company_id=current_user.company_id)
    
    # Apply filters
    if status_filter:
        try:
            status_enum = InvoiceStatus(status_filter)
            query = query.filter(Invoice.status == status_enum)
        except ValueError:
            pass
    
    if project_filter:
        query = query.filter(Invoice.project_id == project_filter)
    
    if overdue_only:
        query = query.filter(
            Invoice.due_date < date.today(),
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL])
        )
    
    # Get invoices with pagination
    page = request.args.get('page', 1, type=int)
    invoices = query.order_by(Invoice.issue_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get projects for filter dropdown
    projects = Project.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    # Calculate summary statistics
    stats = {
        'total_invoices': Invoice.query.filter_by(company_id=current_user.company_id).count(),
        'total_amount': db.session.query(func.sum(Invoice.total_amount)).filter_by(company_id=current_user.company_id).scalar() or 0,
        'outstanding_amount': db.session.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
            Invoice.company_id == current_user.company_id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL])
        ).scalar() or 0,
        'overdue_count': Invoice.query.filter(
            Invoice.company_id == current_user.company_id,
            Invoice.due_date < date.today(),
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL])
        ).count()
    }
    
    return render_template('financial/invoices.html',
                         invoices=invoices,
                         projects=projects,
                         stats=stats,
                         invoice_statuses=InvoiceStatus,
                         current_filters={
                             'status': status_filter,
                             'project': project_filter,
                             'overdue': overdue_only
                         })

@financial_bp.route('/invoices/create', methods=['GET', 'POST'])
@login_required
def create_invoice():
    """Create new invoice"""
    if request.method == 'POST':
        try:
            # Generate invoice number
            invoice_number = generate_invoice_number(current_user.company_id)
            
            invoice = Invoice()
            invoice.invoice_number = invoice_number
            invoice.client_name = request.form.get('client_name')
            invoice.client_email = request.form.get('client_email')
            invoice.client_address = request.form.get('client_address')
            invoice.issue_date = datetime.strptime(request.form.get('issue_date'), '%Y-%m-%d').date()
            invoice.due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
            invoice.payment_terms = request.form.get('payment_terms')
            invoice.notes = request.form.get('notes')
            invoice.company_id = current_user.company_id
            invoice.created_by_id = current_user.id
            
            if request.form.get('project_id'):
                invoice.project_id = int(request.form.get('project_id'))
            
            # Calculate amounts (will be updated when items are added)
            invoice.subtotal = Decimal('0')
            invoice.tax_rate = Decimal(request.form.get('tax_rate', '0'))
            invoice.tax_amount = Decimal('0')
            invoice.total_amount = Decimal('0')
            
            db.session.add(invoice)
            db.session.flush()  # Get the invoice ID
            
            # Add invoice items
            item_descriptions = request.form.getlist('item_description[]')
            item_quantities = request.form.getlist('item_quantity[]')
            item_prices = request.form.getlist('item_price[]')
            
            subtotal = Decimal('0')
            for i, description in enumerate(item_descriptions):
                if description.strip():
                    item = InvoiceItem()
                    item.invoice_id = invoice.id
                    item.description = description
                    item.quantity = Decimal(item_quantities[i])
                    item.unit_price = Decimal(item_prices[i])
                    item.line_total = item.quantity * item.unit_price
                    
                    subtotal += item.line_total
                    db.session.add(item)
            
            # Update invoice totals
            invoice.subtotal = subtotal
            invoice.tax_amount = subtotal * (invoice.tax_rate / 100)
            invoice.total_amount = subtotal + invoice.tax_amount
            
            db.session.commit()
            
            flash(f'Invoice {invoice.invoice_number} created successfully!', 'success')
            return redirect(url_for('financial.invoice_detail', invoice_id=invoice.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating invoice: {str(e)}")
            flash('Error creating invoice. Please try again.', 'error')
    
    # Get projects for dropdown
    projects = Project.query.filter_by(company_id=current_user.company_id, is_active=True).all()
    
    return render_template('financial/create_invoice.html', projects=projects)

@financial_bp.route('/invoices/<int:invoice_id>')
@login_required
def invoice_detail(invoice_id):
    """Display invoice details"""
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    # Get payments for this invoice
    payments = Payment.query.filter_by(invoice_id=invoice_id).order_by(Payment.payment_date.desc()).all()
    
    return render_template('financial/invoice_detail.html',
                         invoice=invoice,
                         payments=payments)

# Helper functions
def get_total_revenue(company_id, year):
    """Get total revenue for the year"""
    return db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_type == TransactionType.INCOME,
        extract('year', Transaction.transaction_date) == year
    ).scalar() or 0

def get_total_expenses(company_id, year):
    """Get total expenses for the year"""
    return db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        extract('year', Transaction.transaction_date) == year
    ).scalar() or 0

def get_outstanding_invoices(company_id):
    """Get total outstanding invoice amount"""
    return db.session.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
        Invoice.company_id == company_id,
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL])
    ).scalar() or 0

def get_cash_flow(company_id, month, year):
    """Get cash flow for the month"""
    income = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_type == TransactionType.INCOME,
        extract('month', Transaction.transaction_date) == month,
        extract('year', Transaction.transaction_date) == year
    ).scalar() or 0
    
    expenses = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        extract('month', Transaction.transaction_date) == month,
        extract('year', Transaction.transaction_date) == year
    ).scalar() or 0
    
    return income - expenses

def generate_transaction_number(company_id):
    """Generate unique transaction number"""
    # Get current year and month
    now = datetime.now()
    prefix = f"TXN-{now.year:04d}{now.month:02d}"
    
    # Get last transaction number for this company and month
    last_transaction = Transaction.query.filter(
        Transaction.company_id == company_id,
        Transaction.transaction_number.like(f"{prefix}%")
    ).order_by(Transaction.transaction_number.desc()).first()
    
    if last_transaction:
        # Extract sequence number and increment
        last_seq = int(last_transaction.transaction_number.split('-')[-1])
        new_seq = last_seq + 1
    else:
        new_seq = 1
    
    return f"{prefix}-{new_seq:04d}"

def generate_invoice_number(company_id):
    """Generate unique invoice number"""
    # Get current year
    year = datetime.now().year
    prefix = f"INV-{year}"
    
    # Get last invoice number for this company and year
    last_invoice = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.invoice_number.like(f"{prefix}%")
    ).order_by(Invoice.invoice_number.desc()).first()
    
    if last_invoice:
        # Extract sequence number and increment
        last_seq = int(last_invoice.invoice_number.split('-')[-1])
        new_seq = last_seq + 1
    else:
        new_seq = 1
    
    return f"{prefix}-{new_seq:04d}"

# API endpoints
@financial_bp.route('/api/financial/dashboard-stats')
@login_required
def financial_dashboard_stats():
    """API endpoint for financial dashboard statistics"""
    try:
        current_year = date.today().year
        current_month = date.today().month
        
        stats = {
            'total_revenue': float(get_total_revenue(current_user.company_id, current_year)),
            'total_expenses': float(get_total_expenses(current_user.company_id, current_year)),
            'outstanding_invoices': float(get_outstanding_invoices(current_user.company_id)),
            'cash_flow': float(get_cash_flow(current_user.company_id, current_month, current_year))
        }
        
        # Monthly trends
        monthly_data = []
        for month in range(1, 13):
            revenue = get_total_revenue(current_user.company_id, current_year) if month <= current_month else 0
            expenses = get_total_expenses(current_user.company_id, current_year) if month <= current_month else 0
            monthly_data.append({
                'month': month,
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(revenue - expenses)
            })
        
        stats['monthly_trends'] = monthly_data
        
        return jsonify(stats)
        
    except Exception as e:
        logging.error(f"Error getting financial stats: {str(e)}")
        return jsonify({'error': 'Failed to load statistics'}), 500