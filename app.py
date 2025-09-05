import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from extensions import db, login_manager, migrate, csrf
from config import Config

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
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
    from blueprints.scheduling import scheduling_bp
    from blueprints.azure_integration import azure_bp
    from blueprints.reports import reports_bp
    from blueprints.admin import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(projects_bp, url_prefix='/projects')
    app.register_blueprint(scheduling_bp, url_prefix='/scheduling')
    app.register_blueprint(azure_bp, url_prefix='/azure')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Register main routes
    from routes import main_bp
    app.register_blueprint(main_bp)
    
    # Add datetime to template context
    from datetime import datetime
    @app.context_processor
    def utility_processor():
        return dict(datetime=datetime)
    
    # Create database tables
    with app.app_context():
        import models  # Import models to ensure they're registered
        db.create_all()
        logging.info("Database tables created successfully")
    
    return app

# Create the application instance
app = create_app()
