import os
from datetime import timedelta

class Config:
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql://localhost/bbschedule")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # Azure configuration
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID")
    
    # Microsoft Fabric configuration
    FABRIC_WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID")
    FABRIC_CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID")
    FABRIC_CLIENT_SECRET = os.environ.get("FABRIC_CLIENT_SECRET")
    
    # Azure AI Foundry configuration
    FOUNDRY_ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT")
    FOUNDRY_API_KEY = os.environ.get("FOUNDRY_API_KEY")
    FOUNDRY_MODEL_NAME = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-4")
    
    # Celery configuration
    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Upload configuration
    UPLOAD_FOLDER = "uploads"
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Security configuration
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
