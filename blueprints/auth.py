from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Company, User, UserRole

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username, is_active=True).first()

        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            # Update last login
            user.last_login = db.func.now()
            db.session.commit()

            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Self-registration, which creates a new company.

    Two things were wrong here, both reachable without a session.

    The company was created and flushed before any field was validated, so an
    empty POST inserted ``Company(name=None)`` and raised IntegrityError — a
    500 on an unauthenticated endpoint. A request carrying a company name but
    no password got as far as creating the company and then bailed on the
    password check, leaving an orphan company behind.

    More seriously, a registration naming an *existing* company joined it::

        company = Company.query.filter_by(name=company_name).first()
        ...
        user.role = PROJECT_MANAGER if not company.users else SCHEDULER

    So anyone who guessed a customer's company name received a scheduler
    account inside that tenant, and with it every project the tenant owns.
    Joining an existing company is an invitation, issued by an administrator of
    that company from the users page — never something a stranger asserts about
    themselves.
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        company_name = (request.form.get("company_name") or "").strip()

        # Validate everything before writing anything.
        required = {
            "username": username,
            "email": email,
            "password": password,
            "first name": first_name,
            "last name": last_name,
            "company name": company_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            flash(f"Please provide: {', '.join(missing)}.", "error")
            return render_template("auth/register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("auth/register.html")

        # Registration creates a company. It never joins one.
        if Company.query.filter_by(name=company_name).first():
            flash(
                "An organisation with that name is already registered. Ask one of its "
                "administrators to create an account for you.",
                "error",
            )
            return render_template("auth/register.html")

        try:
            company = Company()
            company.name = company_name
            db.session.add(company)
            db.session.flush()

            user = User()
            user.username = username
            user.email = email
            user.password_hash = generate_password_hash(password)
            user.first_name = first_name
            user.last_name = last_name
            user.company_id = company.id
            # Sole member of a brand new company, so an administrator of it.
            user.role = UserRole.ADMIN
            user.is_active = True

            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Registration failed")
            flash("Registration could not be completed. Please try again.", "error")
            return render_template("auth/register.html")

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")
