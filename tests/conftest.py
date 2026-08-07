"""Shared fixtures. Every test runs against an isolated in-memory database."""

import os

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SESSION_SECRET", "testing-secret-key")


@pytest.fixture(scope="session")
def flask_app():
    from app import create_app
    from config.production import TestingConfig

    application = create_app(TestingConfig)
    return application


@pytest.fixture
def app_context(flask_app):
    from extensions import db

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded(app_context):
    """A demo project loaded into a clean database."""
    from seed_demo import seed

    project = seed()
    return project


@pytest.fixture
def client(app_context):
    return app_context.test_client()


@pytest.fixture
def signed_in(client, seeded):
    """A test client authenticated as the demo project manager."""
    from models import User

    user = User.query.filter_by(username="demo").first()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
    return client, seeded, user
