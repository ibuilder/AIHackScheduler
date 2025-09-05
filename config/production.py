import os
from datetime import timedelta

class ProductionConfig:
    """Production configuration for BBSchedule Platform"""
    
    # Basic Flask configuration
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('SESSION_SECRET')
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = False  # Disable query recording in production
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,           # Connection pool size
        'pool_timeout': 20,        # Connection timeout
        'pool_recycle': 1800,      # Recycle connections every 30 minutes
        'pool_pre_ping': True,     # Verify connections before use
        'max_overflow': 0,         # Don't allow overflow connections
    }
    
    # Security configuration
    SESSION_COOKIE_SECURE = True      # HTTPS only cookies
    SESSION_COOKIE_HTTPONLY = True    # Prevent XSS access to cookies
    SESSION_COOKIE_SAMESITE = 'Lax'   # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # 8 hour sessions
    
    # Upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file upload
    UPLOAD_FOLDER = '/tmp/uploads'
    
    # Cache configuration
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Rate limiting configuration
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    RATELIMIT_STRATEGY = 'fixed-window-elastic-expiry'
    RATELIMIT_HEADERS_ENABLED = True
    
    # Logging configuration
    LOG_LEVEL = 'INFO'
    LOG_FILE = '/var/log/bbschedule/app.log'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # Azure/Power BI configuration
    POWERBI_CLIENT_ID = os.environ.get('POWERBI_CLIENT_ID')
    POWERBI_CLIENT_SECRET = os.environ.get('POWERBI_CLIENT_SECRET')
    POWERBI_TENANT_ID = os.environ.get('POWERBI_TENANT_ID')
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Celery configuration (for background tasks)
    CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TIMEZONE = 'UTC'
    CELERY_ENABLE_UTC = True
    
    # Security headers configuration
    TALISMAN_CONFIG = {
        'force_https': True,
        'strict_transport_security': True,
        'strict_transport_security_max_age': 31536000,  # 1 year
        'content_security_policy': {
            'default-src': "'self'",
            'script-src': [
                "'self'",
                "'unsafe-inline'",  # Required for some Bootstrap components
                'https://cdn.jsdelivr.net',
                'https://cdnjs.cloudflare.com'
            ],
            'style-src': [
                "'self'",
                "'unsafe-inline'",  # Required for dynamic styles
                'https://cdn.jsdelivr.net',
                'https://cdnjs.cloudflare.com'
            ],
            'img-src': ["'self'", 'data:', 'https:'],
            'font-src': ["'self'", 'https://cdn.jsdelivr.net'],
            'connect-src': ["'self'", 'https://api.powerbi.com', 'https://login.microsoftonline.com']
        },
        'referrer_policy': 'strict-origin-when-cross-origin'
    }
    
    # Performance monitoring
    ENABLE_PROFILER = False  # Disable profiling in production
    PROFILE_DIR = '/var/log/bbschedule/profiles'
    
    # Feature flags
    ENABLE_AUDIT_LOGGING = True
    ENABLE_RATE_LIMITING = True
    ENABLE_CACHING = True
    ENABLE_POWERBI_INTEGRATION = True
    ENABLE_AZURE_INTEGRATION = True
    
    # Backup configuration
    BACKUP_SCHEDULE = '0 2 * * *'  # Daily at 2 AM
    BACKUP_RETENTION_DAYS = 30
    BACKUP_S3_BUCKET = os.environ.get('BACKUP_S3_BUCKET')
    
    # Monitoring and alerting
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    NEW_RELIC_LICENSE_KEY = os.environ.get('NEW_RELIC_LICENSE_KEY')
    
    @staticmethod
    def validate_config():
        """Validate that required configuration is present"""
        required_vars = [
            'DATABASE_URL'
        ]
        
        # Check for either SECRET_KEY or SESSION_SECRET
        secret_key = os.environ.get('SECRET_KEY') or os.environ.get('SESSION_SECRET')
        if not secret_key:
            required_vars.append('SECRET_KEY or SESSION_SECRET')
        
        missing_vars = []
        for var in required_vars:
            if var == 'SECRET_KEY or SESSION_SECRET':
                continue  # Already handled above
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True

class DevelopmentConfig:
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    SQLALCHEMY_ECHO = False  # Set to True for SQL query logging
    
    # Cache (simple in-memory for development)
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 60
    
    # Disable HTTPS requirements in development
    SESSION_COOKIE_SECURE = False
    
    # Logging
    LOG_LEVEL = 'DEBUG'
    
    # Feature flags (enable everything for testing)
    ENABLE_AUDIT_LOGGING = True
    ENABLE_RATE_LIMITING = False  # Disable rate limiting for easier development
    ENABLE_CACHING = True
    ENABLE_POWERBI_INTEGRATION = True
    ENABLE_AZURE_INTEGRATION = True

def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')  # Default to development
    
    if env == 'production':
        return ProductionConfig
    else:
        return DevelopmentConfig