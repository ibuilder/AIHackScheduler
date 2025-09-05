import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from extensions import db, login_manager, migrate, csrf
from config.production import get_config

# Configure comprehensive logging
def setup_logging(app):
    if not app.debug and not app.testing:
        # Production logging setup
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        # Error log file
        file_handler = RotatingFileHandler('logs/bbschedule.log', maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        # Set app log level
        app.logger.setLevel(logging.INFO)
        app.logger.info('BBSchedule Platform startup')
    
    # Development logging - always setup file logging
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('logs/bbschedule-dev.log')
            ]
        )
    
    # Always create logs directory
    if not os.path.exists('logs'):
        os.mkdir('logs')

def setup_enterprise_features(app):
    """Setup enterprise-grade features"""
    
    # Import enterprise modules
    from security.rate_limiting import SecurityMiddleware
    from caching.cache_manager import cache_manager
    from audit.audit_logger import audit_logger
    from database.optimizations import db_optimizer
    from monitoring.health_checks import health_bp
    
    # Security enhancements
    SecurityMiddleware(app)
    
    # Setup Talisman for security headers if in production
    if not app.config.get('DEBUG', False):
        talisman_config = app.config.get('TALISMAN_CONFIG', {})
        Talisman(app, **talisman_config)
    
    # Initialize caching
    if app.config.get('ENABLE_CACHING', True):
        cache_manager.init_app(app)
        app.logger.info("Caching system initialized")
    
    # Initialize database optimizations
    if not app.config.get('DEBUG', False):
        try:
            db_optimizer.init_app(app)
            app.logger.info("Database optimizations applied")
        except Exception as e:
            app.logger.warning(f"Database optimization failed: {str(e)}")
    
    # Register health check endpoints
    app.register_blueprint(health_bp, url_prefix='/health')
    
    # Setup rate limiting if enabled
    if app.config.get('ENABLE_RATE_LIMITING', True):
        try:
            from security.rate_limiting import setup_rate_limiting
            setup_rate_limiting(app)
            app.logger.info("Rate limiting configured")
        except Exception as e:
            app.logger.warning(f"Rate limiting setup failed: {str(e)}")
    
    app.logger.info("Enterprise features initialized successfully")

class Base(DeclarativeBase):
    pass

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Load configuration based on environment
    if config_class is None:
        config_class = get_config()
    
    app.config.from_object(config_class)
    
    # Validate configuration for production
    try:
        config_class.validate_config()
    except ValueError as e:
        # Log warning but don't fail in development
        if app.config.get('DEBUG', False):
            print(f"Configuration warning (development mode): {str(e)}")
        else:
            app.logger.error(f"Configuration validation failed: {str(e)}")
            raise
    except AttributeError:
        # Development config doesn't have validate_config method
        pass
    
    # Configure secret key
    app.secret_key = os.environ.get("SESSION_SECRET")
    
    # ProxyFix for proper URL generation with HTTPS
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Configure login manager
    if hasattr(login_manager, 'login_view'):
        login_manager.login_view = 'auth.login'
        login_manager.login_message = 'Please log in to access this page.'
        login_manager.login_message_category = 'info'
    
    # User loader function for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.projects import projects_bp
    from blueprints.project_management import project_mgmt_bp
    from blueprints.scheduling import scheduling_bp
    from blueprints.azure_integration import azure_bp
    from blueprints.powerbi_integration import powerbi_bp
    from blueprints.reports import reports_bp
    from blueprints.admin import admin_bp
    from analytics.advanced_analytics import analytics_bp
    from admin.user_management import admin_bp as user_mgmt_bp
    from blueprints.project_templates import project_templates_bp
    from collaboration.real_time import collaboration_bp
    from reports.executive_dashboard import executive_bp
    from azure_ai.predictive_analytics import azure_ai_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(projects_bp, url_prefix='/projects')
    app.register_blueprint(project_mgmt_bp, url_prefix='/api/projects')
    app.register_blueprint(scheduling_bp, url_prefix='/scheduling')
    app.register_blueprint(azure_bp, url_prefix='/azure')
    app.register_blueprint(powerbi_bp, url_prefix='/api/powerbi')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(user_mgmt_bp, url_prefix='/management')
    app.register_blueprint(project_templates_bp, url_prefix='/project-templates')
    app.register_blueprint(collaboration_bp, url_prefix='/collaboration')
    app.register_blueprint(executive_bp, url_prefix='/')
    app.register_blueprint(azure_ai_bp, url_prefix='/api')
    
    # Register main routes
    from routes import main_bp
    app.register_blueprint(main_bp)
    
    # Add datetime to template context
    from datetime import datetime
    @app.context_processor
    def utility_processor():
        return dict(datetime=datetime)
    
    # Setup enterprise features
    setup_enterprise_features(app)
    
    # Setup logging
    setup_logging(app)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f'404 error: {request.url}')
        return jsonify({'error': 'Page not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'500 error: {str(error)} at {request.url}', exc_info=True)
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        app.logger.warning(f'403 error: Forbidden access to {request.url}')
        return jsonify({'error': 'Access forbidden'}), 403
    
    @app.errorhandler(429)
    def rate_limit_error(error):
        app.logger.warning(f'Rate limit exceeded: {request.url} from {request.remote_addr}')
        return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429
    
    # Create database tables
    with app.app_context():
        import models  # Import models to ensure they're registered
        db.create_all()
        app.logger.info("Database tables created successfully")
    
    return app

# Create the application instance
app = create_app()
