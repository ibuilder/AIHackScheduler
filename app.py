import logging
import os
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify, render_template, request
from flask_talisman import Talisman
from jinja2 import TemplateNotFound
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

from config.production import get_config
from extensions import csrf, db, login_manager, migrate


# Configure comprehensive logging
def setup_logging(app):
    if not app.debug and not app.testing:
        # Production logging setup
        if not os.path.exists("logs"):
            os.mkdir("logs")

        # Error log file
        file_handler = RotatingFileHandler("logs/bbschedule.log", maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]")
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        # Set app log level
        app.logger.setLevel(logging.INFO)
        app.logger.info("BBSchedule Platform startup")

    # Development logging - always setup file logging
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]",
            handlers=[logging.StreamHandler(), logging.FileHandler("logs/bbschedule-dev.log")],
        )

    # Always create logs directory
    if not os.path.exists("logs"):
        os.mkdir("logs")


def setup_enterprise_features(app):
    """Setup enterprise-grade features"""

    # Import enterprise modules
    from caching.cache_manager import cache_manager
    from database.optimizations import db_optimizer
    from monitoring.health_checks import health_bp
    from security.rate_limiting import SecurityMiddleware

    # Security enhancements
    SecurityMiddleware(app)

    # Talisman enforces HTTPS and CSP. It is skipped in debug and under test:
    # its default force_https turned every test request into a 302 to
    # https://localhost, and the config carries no TALISMAN_CONFIG outside
    # production, so it would have run on bare defaults regardless.
    if not app.config.get("DEBUG", False) and not app.config.get("TESTING", False):
        talisman_config = app.config.get("TALISMAN_CONFIG")
        if talisman_config:
            Talisman(app, **talisman_config)
        else:
            app.logger.warning(
                "TALISMAN_CONFIG is not set for this environment; "
                "skipping security headers rather than applying untested defaults."
            )

    # Initialize caching
    if app.config.get("ENABLE_CACHING", True):
        cache_manager.init_app(app)
        app.logger.info("Caching system initialized")

    # Initialize database optimizations
    if not app.config.get("DEBUG", False):
        try:
            db_optimizer.init_app(app)
            app.logger.info("Database optimizations applied")
        except Exception as e:
            app.logger.warning(f"Database optimization failed: {str(e)}")

    # Register health check endpoints
    app.register_blueprint(health_bp, url_prefix="/health")

    # Setup rate limiting if enabled
    if app.config.get("ENABLE_RATE_LIMITING", True):
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
        if app.config.get("DEBUG", False):
            print(f"Configuration warning (development mode): {str(e)}")
        else:
            app.logger.error(f"Configuration validation failed: {str(e)}")
            raise
    except AttributeError:
        # Development config doesn't have validate_config method
        pass

    # The secret key comes from the config class, which already resolves
    # SECRET_KEY then SESSION_SECRET and supplies a development default.
    # Reading the environment again here overwrote it with None whenever only
    # the config default was available, breaking sessions and flash messages.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "No SECRET_KEY configured. Set SECRET_KEY or SESSION_SECRET in the environment."
        )

    # ProxyFix for proper URL generation with HTTPS
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    # render_as_batch rebuilds a table to apply an ALTER, which SQLite cannot
    # do directly. Development runs on SQLite, so without this every migration
    # that changes a column fails there while working fine on PostgreSQL.
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)

    # Configure login manager
    if hasattr(login_manager, "login_view"):
        login_manager.login_view = "auth.login"
        login_manager.login_message = "Please log in to access this page."
        login_manager.login_message_category = "info"

    # User loader function for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from models import User

        return User.query.get(int(user_id))

    # Register blueprints
    from admin.user_management import admin_bp as user_mgmt_bp
    from analytics.advanced_analytics import analytics_bp
    from azure_ai.predictive_analytics import azure_ai_bp
    from blueprints.admin import admin_bp
    from blueprints.auth import auth_bp
    from blueprints.azure_integration import azure_bp
    from blueprints.equipment_management import equipment_bp
    from blueprints.financial_management import financial_bp
    from blueprints.powerbi_integration import powerbi_bp
    from blueprints.project_management import project_mgmt_bp
    from blueprints.project_templates import project_templates_bp
    from blueprints.projects import projects_bp
    from blueprints.reports import reports_bp
    from blueprints.schedule_api import schedule_api_bp
    from blueprints.scheduling import scheduling_bp
    from collaboration.real_time import collaboration_bp
    from reports.executive_dashboard import executive_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(project_mgmt_bp, url_prefix="/api/projects")
    app.register_blueprint(scheduling_bp, url_prefix="/scheduling")
    app.register_blueprint(azure_bp, url_prefix="/azure")
    app.register_blueprint(powerbi_bp, url_prefix="/api/powerbi")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(user_mgmt_bp, url_prefix="/management")
    app.register_blueprint(project_templates_bp, url_prefix="/project-templates")
    app.register_blueprint(collaboration_bp, url_prefix="/collaboration")
    app.register_blueprint(executive_bp, url_prefix="/")
    app.register_blueprint(azure_ai_bp, url_prefix="/api")
    app.register_blueprint(equipment_bp, url_prefix="/")
    app.register_blueprint(financial_bp, url_prefix="/")
    app.register_blueprint(schedule_api_bp, url_prefix="/api/schedule")

    # CSRF protection is built around form posts and cannot be satisfied by a
    # JSON fetch carrying no hidden field. This blueprint is exempted and
    # defended instead by the session cookie's SameSite=Lax policy, which stops
    # a cross-site POST carrying credentials at all, plus the JSON body each
    # mutating view requires — a cross-origin caller cannot set that
    # content-type without a CORS preflight this application never answers.
    csrf.exempt(schedule_api_bp)

    # Register main routes
    from routes import main_bp

    app.register_blueprint(main_bp)

    # Add datetime to template context
    from datetime import date, datetime, timedelta

    @app.context_processor
    def utility_processor():
        # Templates already used date.today() and timedelta without either
        # being injected, so Jinja resolved them to Undefined and the page
        # raised UndefinedError on render.
        return {"datetime": datetime, "date": date, "timedelta": timedelta}

    # Setup enterprise features
    setup_enterprise_features(app)

    # Setup logging
    setup_logging(app)

    # Error handlers. These content-negotiate: API clients get JSON, browsers
    # get a rendered page. Previously every 404 returned JSON, so a mistyped
    # URL showed raw JSON instead of an error page.
    def _wants_json():
        if request.path.startswith("/api/") or request.is_json:
            return True
        accept = request.accept_mimetypes
        return accept["application/json"] >= accept["text/html"]

    def _error_response(message, status, template="errors/error.html"):
        if _wants_json():
            return jsonify({"error": message}), status
        try:
            return render_template(template, message=message, status=status), status
        except TemplateNotFound:
            return message, status

    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning("404: %s", request.url)
        return _error_response("Page not found", 404)

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("500 at %s: %s", request.url, error, exc_info=True)
        db.session.rollback()
        return _error_response("Internal server error", 500)

    @app.errorhandler(403)
    def forbidden_error(error):
        app.logger.warning("403: forbidden access to %s", request.url)
        return _error_response("Access forbidden", 403)

    @app.errorhandler(429)
    def rate_limit_error(error):
        app.logger.warning(
            "429: rate limit exceeded on %s from %s", request.url, request.remote_addr
        )
        return _error_response("Rate limit exceeded. Please try again later.", 429)

    # Schema creation is a deliberate step, not an import side effect.
    # Flask-Migrate owns the schema in every environment that persists data;
    # `flask init-db` covers local development and tests.
    if app.config.get("AUTO_CREATE_TABLES", app.config.get("TESTING", False)):
        with app.app_context():
            import models  # noqa: F401  -- registers the mappers

            db.create_all()
            app.logger.info("Database tables created")

    register_cli(app)

    return app


def register_cli(app):
    """Management commands: `flask init-db` and `flask seed-demo`."""

    @app.cli.command("init-db")
    def init_db():
        """Create every table from the current models, for a scratch database.

        Prefer `flask db upgrade`, which is what deployments run. create_all
        only adds missing tables — it never alters an existing one — so on a
        database from an earlier release it silently leaves old columns and
        constraints in place. This stays for throwaway local databases and for
        the test fixtures, which build from scratch every time.
        """
        import models  # noqa: F401

        db.create_all()
        # Mark it current so a later `db upgrade` does not try to re-run
        # migrations against a schema that already has everything.
        try:
            from flask_migrate import stamp

            stamp()
            stamped = " and stamped at head"
        except Exception as exc:  # pragma: no cover - only if alembic is absent
            stamped = f" (could not stamp: {exc})"

        print(f"Schema created in {app.config['SQLALCHEMY_DATABASE_URI']}{stamped}")
        print("For anything you intend to keep, use: flask db upgrade")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Load the demo company, project and schedule."""
        from seed_demo import seed

        seed()

    @app.cli.command("import-schedule")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    @click.option("--company", type=int, required=True, help="Company id to import into.")
    @click.option("--user", type=int, required=True, help="User id to record as the creator.")
    @click.option("--name", default=None, help="Override the project name.")
    def import_schedule_command(path, company, user, name):
        """Import a .xer, .xml (MSPDI) or .mpp file as a new project."""
        from pathlib import Path

        from services.schedule_io import import_into_project, read_schedule_file

        data = Path(path).read_bytes()
        schedule = read_schedule_file(data, Path(path).name)

        for warning in schedule.warnings:
            click.echo(f"  warning: {warning}")

        project = import_into_project(schedule, company_id=company, user_id=user, project_name=name)
        summary = schedule.summary()
        click.echo(f"Imported '{project.name}' as project {project.id}")
        click.echo(
            f"  {summary['activities']} activities, {summary['relationships']} relationships"
        )
        click.echo(f"  relationship types: {summary['relationship_types']}")

    @app.cli.command("export-schedule")
    @click.argument("project_id", type=int)
    @click.option(
        "--format",
        "export_format",
        type=click.Choice(["xer", "mspdi"]),
        default="xer",
        help="mspdi writes Microsoft Project XML. The binary .mpp cannot be written.",
    )
    @click.option("--out", "out_path", default=None, help="Where to write. Defaults to cwd.")
    def export_schedule_command(project_id, export_format, out_path):
        """Export a project as Primavera XER or Microsoft Project XML."""
        from pathlib import Path

        from services.schedule_io import export_project, serialise

        schedule = export_project(project_id)
        content, filename, _ = serialise(schedule, export_format)

        destination = Path(out_path) if out_path else Path(filename)
        destination.write_text(content, encoding="utf-8")
        click.echo(f"Wrote {destination} ({len(content)} bytes)")

    @app.cli.command("schedule-formats")
    def schedule_formats_command():
        """Show which schedule file formats this deployment can read and write."""
        from services.schedule_io import capabilities

        caps = capabilities()
        click.echo("Read:")
        for name, available in caps["read"].items():
            click.echo(f"  {name:<6} {'yes' if available else 'no'}")
        click.echo("Write:")
        for name, available in caps["write"].items():
            click.echo(f"  {name:<6} {'yes' if available else 'no'}")
        for note in caps["notes"].values():
            click.echo("")
            click.echo(f"  {note}")


# WSGI entry point. Gunicorn and the Flask CLI both import this name.
app = create_app()
