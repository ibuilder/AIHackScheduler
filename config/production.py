"""Application configuration by environment.

Kept at this module path because ``app.py`` imports ``get_config`` from here.
It now also carries the Azure/Fabric/Foundry settings that used to live in a
root-level ``config.py`` — that file was shadowed by this package and had
never been loaded.
"""

import os
from datetime import timedelta


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload limits
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

    # Azure
    AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
    AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID")

    # Microsoft Fabric
    FABRIC_WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID")
    FABRIC_CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID")
    FABRIC_CLIENT_SECRET = os.environ.get("FABRIC_CLIENT_SECRET")

    # Azure AI Foundry / OpenAI-compatible endpoint
    FOUNDRY_ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT")
    FOUNDRY_API_KEY = os.environ.get("FOUNDRY_API_KEY")
    FOUNDRY_MODEL_NAME = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-4o")

    # Power BI
    POWERBI_CLIENT_ID = os.environ.get("POWERBI_CLIENT_ID")
    POWERBI_CLIENT_SECRET = os.environ.get("POWERBI_CLIENT_SECRET")
    POWERBI_TENANT_ID = os.environ.get("POWERBI_TENANT_ID")

    # Redis / Celery
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TIMEZONE = "UTC"
    CELERY_ENABLE_UTC = True

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("true", "on", "1")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")

    # Observability
    SENTRY_DSN = os.environ.get("SENTRY_DSN")


class ProductionConfig(BaseConfig):
    """Production configuration. Fails fast on missing secrets."""

    DEBUG = False
    TESTING = False

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_RECORD_QUERIES = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,
        "pool_timeout": 20,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
        "max_overflow": 0,
    }

    # Session security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Cache
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = BaseConfig.REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300

    # Rate limiting
    RATELIMIT_STORAGE_URL = BaseConfig.REDIS_URL
    RATELIMIT_STRATEGY = "fixed-window-elastic-expiry"
    RATELIMIT_HEADERS_ENABLED = True

    LOG_LEVEL = "INFO"
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 5

    TALISMAN_CONFIG = {
        "force_https": True,
        "strict_transport_security": True,
        "strict_transport_security_max_age": 31536000,
        "content_security_policy": {
            "default-src": "'self'",
            "script-src": [
                "'self'",
                "'unsafe-inline'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
            ],
            "style-src": [
                "'self'",
                "'unsafe-inline'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
            ],
            "img-src": ["'self'", "data:", "https:"],
            "font-src": ["'self'", "https://cdn.jsdelivr.net"],
            "connect-src": [
                "'self'",
                "https://api.powerbi.com",
                "https://login.microsoftonline.com",
            ],
        },
        "referrer_policy": "strict-origin-when-cross-origin",
    }

    ENABLE_PROFILER = False
    ENABLE_AUDIT_LOGGING = True
    ENABLE_RATE_LIMITING = True
    ENABLE_CACHING = True
    ENABLE_POWERBI_INTEGRATION = True
    ENABLE_AZURE_INTEGRATION = True

    BACKUP_SCHEDULE = "0 2 * * *"
    BACKUP_RETENTION_DAYS = 30
    BACKUP_S3_BUCKET = os.environ.get("BACKUP_S3_BUCKET")

    @staticmethod
    def validate_config():
        """Refuse to start production without the secrets that matter."""
        missing = []

        if not (os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET")):
            missing.append("SECRET_KEY or SESSION_SECRET")
        if not os.environ.get("DATABASE_URL"):
            missing.append("DATABASE_URL")

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return True


class DevelopmentConfig(BaseConfig):
    """Development configuration.

    Falls back to a local SQLite file so the application runs immediately
    after a clone, with no PostgreSQL or Redis to install first.
    """

    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-secret-key-not-for-production")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///bbschedule-dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.environ.get("SQL_ECHO", "").lower() in ("1", "true")

    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 60

    RATELIMIT_STORAGE_URL = "memory://"

    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = "DEBUG"

    ENABLE_AUDIT_LOGGING = True
    ENABLE_RATE_LIMITING = False  # noisy during development
    ENABLE_CACHING = True
    ENABLE_POWERBI_INTEGRATION = True
    ENABLE_AZURE_INTEGRATION = True


class TestingConfig(DevelopmentConfig):
    """In-memory database, no caching, CSRF off so tests can post forms."""

    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "NullCache"
    ENABLE_CACHING = False
    ENABLE_RATE_LIMITING = False
    SECRET_KEY = "testing-secret-key"


_CONFIGS = {
    "production": ProductionConfig,
    "testing": TestingConfig,
    "development": DevelopmentConfig,
}


def get_config(env=None):
    """Resolve the config class for ``FLASK_ENV`` (default: development)."""
    env = env or os.environ.get("FLASK_ENV", "development")
    return _CONFIGS.get(env, DevelopmentConfig)
