from flask import request, current_app
from flask_login import current_user
from datetime import datetime, timezone
from extensions import db
import json
import logging

class AuditLogger:
    """Enterprise audit logging system"""
    
    def __init__(self):
        self.enabled = True
    
    def log_action(self, action, resource_type=None, resource_id=None, details=None, user_id=None, company_id=None):
        """Log a user action to the audit trail"""
        if not self.enabled:
            return
        
        try:
            # Import AuditLog model to avoid circular imports
            from models import AuditLog
            
            # Get current user info
            if not user_id and hasattr(current_user, 'id'):
                user_id = current_user.id if current_user.is_authenticated else None
                
            if not company_id and hasattr(current_user, 'company_id'):
                company_id = current_user.company_id if current_user.is_authenticated else None
            
            # Create audit log entry
            audit_entry = AuditLog()
            audit_entry.user_id = user_id
            audit_entry.company_id = company_id
            audit_entry.action = action
            audit_entry.resource_type = resource_type
            audit_entry.resource_id = resource_id
            audit_entry.details = json.dumps(details) if details else None
            audit_entry.ip_address = request.remote_addr if request else None
            audit_entry.user_agent = request.user_agent.string if request and request.user_agent else None
            
            db.session.add(audit_entry)
            db.session.commit()
            
            # Also log to application logs
            log_msg = f"AUDIT: {action}"
            if resource_type and resource_id:
                log_msg += f" {resource_type}:{resource_id}"
            if user_id:
                log_msg += f" by user:{user_id}"
            
            current_app.logger.info(log_msg)
            
        except Exception as e:
            # Don't let audit logging break the application
            current_app.logger.error(f"Audit logging failed: {str(e)}")
            try:
                db.session.rollback()
            except:
                pass
    
    def log_login(self, user_id, success=True):
        """Log login attempts"""
        action = "login_success" if success else "login_failed" 
        self.log_action(action, resource_type="user", resource_id=user_id)
    
    def log_logout(self, user_id):
        """Log logout"""
        self.log_action("logout", resource_type="user", resource_id=user_id)
    
    def log_project_action(self, action, project_id, details=None):
        """Log project-related actions"""
        self.log_action(action, resource_type="project", resource_id=project_id, details=details)
    
    def log_task_action(self, action, task_id, details=None):
        """Log task-related actions"""
        self.log_action(action, resource_type="task", resource_id=task_id, details=details)
    
    def log_user_management(self, action, target_user_id, details=None):
        """Log user management actions"""
        self.log_action(action, resource_type="user", resource_id=target_user_id, details=details)
    
    def log_security_event(self, event_type, details=None):
        """Log security events"""
        self.log_action(f"security_{event_type}", details=details)
    
    def log_data_export(self, export_type, resource_ids=None):
        """Log data export actions"""
        details = {"export_type": export_type}
        if resource_ids:
            details["resource_ids"] = resource_ids
        self.log_action("data_export", details=details)
    
    def log_integration_action(self, action, service_type, details=None):
        """Log integration actions (Power BI, Azure, etc.)"""
        integration_details = {"service_type": service_type}
        if details:
            integration_details.update(details)
        self.log_action(f"integration_{action}", resource_type="integration", details=integration_details)
    
    def get_user_activity(self, user_id, limit=100):
        """Get recent activity for a user"""
        try:
            from models import AuditLog
            return AuditLog.query.filter_by(user_id=user_id)\
                .order_by(AuditLog.timestamp.desc())\
                .limit(limit).all()
        except Exception as e:
            current_app.logger.error(f"Failed to get user activity: {str(e)}")
            return []
    
    def get_resource_history(self, resource_type, resource_id, limit=50):
        """Get audit history for a specific resource"""
        try:
            from models import AuditLog
            return AuditLog.query.filter_by(resource_type=resource_type, resource_id=resource_id)\
                .order_by(AuditLog.timestamp.desc())\
                .limit(limit).all()
        except Exception as e:
            current_app.logger.error(f"Failed to get resource history: {str(e)}")
            return []
    
    def get_company_activity(self, company_id, limit=200):
        """Get recent activity for a company"""
        try:
            from models import AuditLog
            return AuditLog.query.filter_by(company_id=company_id)\
                .order_by(AuditLog.timestamp.desc())\
                .limit(limit).all()
        except Exception as e:
            current_app.logger.error(f"Failed to get company activity: {str(e)}")
            return []

# Global audit logger instance
audit_logger = AuditLogger()

def log_action(action, **kwargs):
    """Convenience function for logging actions"""
    audit_logger.log_action(action, **kwargs)