"""
Real-time Collaboration Features for BBSchedule Platform
AJAX-based real-time updates and team collaboration
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone
from models import Project, Task, User, Company
from extensions import db
from audit.audit_logger import audit_logger
import json
import logging

collaboration_bp = Blueprint('collaboration', __name__)

class CollaborationManager:
    """Manages real-time collaboration features"""
    
    def __init__(self):
        self.active_users = {}  # Track active users per project
        self.project_rooms = {}  # Track project room memberships
        self.recent_messages = {}  # Store recent messages per project
    
    def register_user_activity(self, project_id, user_id, activity_type, details=None):
        """Register user activity for a project"""
        if project_id not in self.project_rooms:
            self.project_rooms[project_id] = {
                'active_users': [],
                'last_activity': datetime.now(timezone.utc),
                'activities': []
            }
        
        # Add activity
        activity = {
            'user_id': user_id,
            'type': activity_type,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Keep only last 50 activities
        self.project_rooms[project_id]['activities'].append(activity)
        if len(self.project_rooms[project_id]['activities']) > 50:
            self.project_rooms[project_id]['activities'].pop(0)
        
        self.project_rooms[project_id]['last_activity'] = datetime.now(timezone.utc)
    
    def add_project_message(self, project_id, user_id, username, message):
        """Add a message to project chat"""
        if project_id not in self.recent_messages:
            self.recent_messages[project_id] = []
        
        message_data = {
            'user_id': user_id,
            'username': username,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.recent_messages[project_id].append(message_data)
        
        # Keep only last 100 messages
        if len(self.recent_messages[project_id]) > 100:
            self.recent_messages[project_id].pop(0)
        
        # Register activity
        self.register_user_activity(project_id, user_id, 'message', {'message': message})
        
        return message_data
    
    def get_project_messages(self, project_id):
        """Get recent messages for a project"""
        return self.recent_messages.get(project_id, [])
    
    def get_project_activities(self, project_id):
        """Get recent activities for a project"""
        if project_id not in self.project_rooms:
            return []
        
        activities = self.project_rooms[project_id].get('activities', [])
        
        # Format activities for display
        formatted_activities = []
        for activity in activities[-10:]:  # Get last 10
            user = User.query.get(activity['user_id'])
            username = user.username if user else 'Unknown User'
            
            if activity['type'] == 'message':
                action = f"Posted: {activity['details'].get('message', '')[:50]}..."
            elif activity['type'] == 'task_update':
                action = f"Updated task: {activity['details'].get('task_name', 'Unknown')}"
            elif activity['type'] == 'file_upload':
                action = f"Uploaded file: {activity['details'].get('filename', 'Unknown')}"
            else:
                action = f"Performed action: {activity['type']}"
            
            formatted_activities.append({
                'user': username,
                'action': action,
                'timestamp': activity['timestamp'].isoformat() if isinstance(activity['timestamp'], datetime) else activity['timestamp']
            })
        
        return formatted_activities
    
    def register_task_update(self, project_id, user_id, task_id, task_name, update_type='update'):
        """Register a task update activity"""
        self.register_user_activity(project_id, user_id, 'task_update', {
            'task_id': task_id,
            'task_name': task_name,
            'update_type': update_type
        })
        
        # Log the activity
        audit_logger.log_action(
            f'task_{update_type}',
            resource_type='task',
            resource_id=task_id,
            details={
                'project_id': project_id,
                'collaboration_tracked': True
            }
        )
    
    def clear_old_data(self):
        """Clear old collaboration data to prevent memory buildup"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # Clear old project rooms
        for project_id in list(self.project_rooms.keys()):
            room = self.project_rooms[project_id]
            if room['last_activity'] < cutoff_time:
                del self.project_rooms[project_id]
        
        # Clear old messages
        for project_id in list(self.recent_messages.keys()):
            messages = self.recent_messages[project_id]
            # Keep only messages from last 24 hours
            recent_messages = [
                msg for msg in messages 
                if datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')) > cutoff_time
            ]
            if recent_messages:
                self.recent_messages[project_id] = recent_messages
            else:
                del self.recent_messages[project_id]
    
    def get_active_users_count(self, project_id):
        """Get count of active users for a project"""
        if project_id in self.project_rooms:
            return len(self.project_rooms[project_id].get('active_users', []))
        return 0

# Global collaboration manager instance
collaboration_manager = CollaborationManager()

@collaboration_bp.route('/api/collaboration/active-users/<int:project_id>')
@login_required
def get_active_users(project_id):
    """Get active users for a project"""
    # Verify project access
    project = Project.query.filter_by(
        id=project_id,
        company_id=current_user.company_id
    ).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get active users from collaboration manager
    if project_id in collaboration_manager.project_rooms:
        active_users = collaboration_manager.project_rooms[project_id]['active_users']
    else:
        active_users = []
    
    return jsonify({
        'project_id': project_id,
        'active_users': active_users,
        'total_count': len(active_users)
    })

@collaboration_bp.route('/api/collaboration/activity/<int:project_id>')
@login_required
def get_project_activity(project_id):
    """Get recent project activity"""
    # Verify project access
    project = Project.query.filter_by(
        id=project_id,
        company_id=current_user.company_id
    ).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    activity = collaboration_manager.get_project_activities(project_id)
    
    return jsonify({
        'project_id': project_id,
        'activity': activity
    })

@collaboration_bp.route('/api/collaboration/messages/<int:project_id>')
@login_required
def get_project_messages(project_id):
    """Get recent project messages"""
    # Verify project access
    project = Project.query.filter_by(
        id=project_id,
        company_id=current_user.company_id
    ).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    messages = collaboration_manager.get_project_messages(project_id)
    
    return jsonify({
        'project_id': project_id,
        'messages': messages
    })

@collaboration_bp.route('/api/collaboration/send-message', methods=['POST'])
@login_required
def send_project_message():
    """Send a message to project chat"""
    data = request.get_json()
    project_id = data.get('project_id')
    message = data.get('message', '').strip()
    
    if not project_id or not message:
        return jsonify({'error': 'Project ID and message required'}), 400
    
    # Verify project access
    project = Project.query.filter_by(
        id=project_id,
        company_id=current_user.company_id
    ).first()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Add message
    message_data = collaboration_manager.add_project_message(
        project_id, current_user.id, current_user.username, message
    )
    
    return jsonify({
        'success': True,
        'message': message_data
    })

from datetime import timedelta