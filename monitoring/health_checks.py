from flask import Blueprint, jsonify, current_app
from extensions import db
from datetime import datetime
import os
import psutil
import logging

health_bp = Blueprint('health', __name__)

@health_bp.route('/health')
def health_check():
    """Basic health check endpoint"""
    try:
        # Check database connectivity
        db.engine.execute('SELECT 1')
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'environment': os.environ.get('FLASK_ENV', 'production')
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

@health_bp.route('/health/detailed')
def detailed_health_check():
    """Detailed health check with system metrics"""
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'environment': os.environ.get('FLASK_ENV', 'production'),
            'checks': {}
        }
        
        # Database check
        try:
            db.engine.execute('SELECT 1')
            health_data['checks']['database'] = {'status': 'healthy', 'response_time_ms': 0}
        except Exception as e:
            health_data['checks']['database'] = {'status': 'unhealthy', 'error': str(e)}
            health_data['status'] = 'unhealthy'
        
        # System metrics
        try:
            health_data['checks']['system'] = {
                'status': 'healthy',
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
        except Exception as e:
            health_data['checks']['system'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Redis check (if configured)
        try:
            import redis
            redis_url = os.environ.get('REDIS_URL')
            if redis_url:
                r = redis.from_url(redis_url)
                r.ping()
                health_data['checks']['redis'] = {'status': 'healthy'}
            else:
                health_data['checks']['redis'] = {'status': 'not_configured'}
        except Exception as e:
            health_data['checks']['redis'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Power BI integration check
        try:
            powerbi_configured = all([
                os.environ.get('POWERBI_CLIENT_ID'),
                os.environ.get('POWERBI_CLIENT_SECRET'), 
                os.environ.get('POWERBI_TENANT_ID')
            ])
            health_data['checks']['powerbi'] = {
                'status': 'configured' if powerbi_configured else 'not_configured'
            }
        except Exception as e:
            health_data['checks']['powerbi'] = {'status': 'error', 'error': str(e)}
        
        status_code = 200 if health_data['status'] == 'healthy' else 503
        return jsonify(health_data), status_code
        
    except Exception as e:
        current_app.logger.error(f"Detailed health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

@health_bp.route('/health/readiness')
def readiness_check():
    """Kubernetes readiness probe endpoint"""
    try:
        # Check if application is ready to serve requests
        db.engine.execute('SELECT 1')
        
        return jsonify({
            'status': 'ready',
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Readiness check failed: {str(e)}")
        return jsonify({
            'status': 'not_ready',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

@health_bp.route('/health/liveness')  
def liveness_check():
    """Kubernetes liveness probe endpoint"""
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'pid': os.getpid()
    }), 200

@health_bp.route('/metrics')
def metrics_endpoint():
    """Prometheus-style metrics endpoint"""
    try:
        from models import User, Project, Task, Company
        
        metrics = []
        
        # Application metrics
        metrics.append(f"bbschedule_users_total {User.query.count()}")
        metrics.append(f"bbschedule_companies_total {Company.query.count()}")
        metrics.append(f"bbschedule_projects_total {Project.query.count()}")
        metrics.append(f"bbschedule_tasks_total {Task.query.count()}")
        
        # System metrics
        if hasattr(psutil, 'cpu_percent'):
            metrics.append(f"bbschedule_cpu_percent {psutil.cpu_percent()}")
        
        if hasattr(psutil, 'virtual_memory'):
            memory = psutil.virtual_memory()
            metrics.append(f"bbschedule_memory_percent {memory.percent}")
            metrics.append(f"bbschedule_memory_used_bytes {memory.used}")
            metrics.append(f"bbschedule_memory_available_bytes {memory.available}")
        
        return '\n'.join(metrics), 200, {'Content-Type': 'text/plain'}
        
    except Exception as e:
        current_app.logger.error(f"Metrics endpoint failed: {str(e)}")
        return f"# Error generating metrics: {str(e)}", 500, {'Content-Type': 'text/plain'}