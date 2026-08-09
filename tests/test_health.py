"""The health endpoints, and the deployment probes that depend on them.

These had never been asserted on. ``db.engine.execute("SELECT 1")`` was removed
in SQLAlchemy 2.0 — the version this project pins — so every database-backed
health endpoint raised ``AttributeError`` and returned 503, always.

Nothing caught it because nothing consumes these endpoints except probes:

* ``deployment/Dockerfile`` — ``HEALTHCHECK`` on ``/health/health``
* ``deployment/docker-compose.yml`` — the same, and the web service is a
  ``depends_on: condition: service_healthy`` target
* ``deployment/azure-deploy.yml`` — Kubernetes liveness and readiness probes

A container built from this repository reported itself unhealthy for its entire
life, and a Kubernetes pod whose readiness probe never passes is never sent
traffic. The tests that assert a probe URL is real, below, are the ones that
tie the deployment files to the code.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT = REPO_ROOT / "deployment"


# ── the endpoints themselves ─────────────────────────────────────────────


def test_the_basic_health_check_reports_healthy(client):
    response = client.get("/health/health")
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["status"] == "healthy"


def test_the_readiness_probe_reports_ready(client):
    response = client.get("/health/health/readiness")
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["status"] == "ready"


def test_the_liveness_probe_reports_alive(client):
    response = client.get("/health/health/liveness")
    assert response.status_code == 200
    assert response.get_json()["status"] == "alive"


def test_the_detailed_check_finds_the_database_healthy(client):
    """The detailed endpoint degrades per subsystem, so a broken database check
    shows up as an unhealthy entry rather than an exception."""
    body = client.get("/health/health/detailed").get_json()
    assert body["checks"]["database"] == {"status": "healthy", "response_time_ms": 0}
    assert body["status"] == "healthy", body["checks"]


def test_metrics_are_served_as_prometheus_text(client):
    response = client.get("/health/metrics")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain")
    assert "bbschedule_projects_total" in response.get_data(as_text=True)


# ── the deployment files agree with the routes ───────────────────────────


def _registered_paths(flask_app) -> set[str]:
    return {str(rule) for rule in flask_app.url_map.iter_rules()}


def test_the_dockerfile_healthcheck_names_a_route_that_exists(flask_app):
    dockerfile = (DEPLOYMENT / "Dockerfile").read_text(encoding="utf-8")
    probed = re.findall(r"localhost:5000(/[\w/-]*)", dockerfile)
    assert probed, "the Dockerfile no longer declares a HEALTHCHECK"
    for path in probed:
        assert path in _registered_paths(flask_app), (
            f"HEALTHCHECK probes {path}, which is not a route"
        )


def test_the_compose_healthcheck_names_a_route_that_exists(flask_app):
    compose = (DEPLOYMENT / "docker-compose.yml").read_text(encoding="utf-8")
    probed = re.findall(r"localhost:5000(/[\w/-]*)", compose)
    assert probed, "the compose file no longer declares a healthcheck"
    for path in probed:
        assert path in _registered_paths(flask_app), f"compose probes {path}, which is not a route"


def test_the_kubernetes_probes_name_routes_that_exist(flask_app):
    """A readiness probe pointing at a route that does not exist means the pod
    never becomes ready, and the deployment silently serves nothing."""
    manifest = (DEPLOYMENT / "azure-deploy.yml").read_text(encoding="utf-8")
    probed = re.findall(r'path:\s*"([^"]+)"', manifest)
    assert probed, "the manifest no longer declares probes"
    for path in probed:
        assert path in _registered_paths(flask_app), f"probe targets {path}, which is not a route"


def test_every_probe_url_actually_returns_success(client, flask_app):
    """Existing as a route is not enough — the probe has to pass. This is the
    check that would have caught the SQLAlchemy 2.0 breakage directly."""
    sources = ["Dockerfile", "docker-compose.yml", "azure-deploy.yml"]
    probed = set()
    for name in sources:
        text = (DEPLOYMENT / name).read_text(encoding="utf-8")
        probed |= set(re.findall(r"localhost:5000(/[\w/-]*)", text))
        probed |= set(re.findall(r'path:\s*"(/[^"]+)"', text))

    assert probed, "no probe URLs found in any deployment file"
    for path in sorted(probed):
        response = client.get(path)
        assert response.status_code == 200, (
            f"{path} is probed by deployment config but returns "
            f"{response.status_code}: {response.get_data(as_text=True)[:200]}"
        )
