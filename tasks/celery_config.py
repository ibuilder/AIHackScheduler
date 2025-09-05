import os
from celery import Celery

def make_celery(app=None):
    """Create Celery instance and configure it."""
    celery = Celery(
        'bbschedule',
        broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        include=['tasks.background_tasks']
    )
    
    # Configure Celery
    celery.conf.update(
        timezone='UTC',
        enable_utc=True,
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        task_routes={
            'tasks.file_processing.*': {'queue': 'file_processing'},
            'tasks.azure_sync.*': {'queue': 'azure_sync'},
            'tasks.notifications.*': {'queue': 'notifications'},
            'tasks.reports.*': {'queue': 'reports'},
        },
        task_annotations={
            '*': {'rate_limit': '10/s'}
        }
    )
    
    if app:
        # Update configuration with Flask app config
        celery.conf.update(app.config)
        
        class ContextTask(celery.Task):
            """Make celery tasks work with Flask app context."""
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        
        celery.Task = ContextTask
    
    return celery

# Create Celery instance
celery_app = make_celery()
