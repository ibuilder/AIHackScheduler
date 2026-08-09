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

import yaml

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
    database = body["checks"]["database"]
    assert database["status"] == "healthy", database
    # A real measurement now, not the hardcoded 0 this used to assert.
    assert isinstance(database["response_time_ms"], (int, float))
    assert database["response_time_ms"] >= 0
    assert body["status"] == "healthy", body["checks"]


def test_metrics_are_served_as_prometheus_text(client):
    response = client.get("/health/metrics")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain")
    assert "bbschedule_projects_total" in response.get_data(as_text=True)


# ── the deployment files agree with the routes ───────────────────────────


def _registered_paths(flask_app) -> set[str]:
    return {str(rule) for rule in flask_app.url_map.iter_rules()}


def _path_from_url(value: str) -> str | None:
    match = re.search(r"localhost:5000(/[\w/-]*)", value)
    return match.group(1) if match else None


# Each reader returns only the URLs the file actually probes. An earlier
# version scanned whole files for anything URL-shaped, which meant an unrelated
# `APP_URL=http://localhost:5000/api` in the compose environment would be
# treated as a probe and required to return 200 — failing the suite over a
# legitimate config change.


def dockerfile_probes() -> list[str]:
    """The URL in the HEALTHCHECK instruction, and nothing else."""
    text = (DEPLOYMENT / "Dockerfile").read_text(encoding="utf-8")
    # HEALTHCHECK may be continued across lines with a trailing backslash.
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    found = []
    for line in joined.splitlines():
        if line.strip().upper().startswith("HEALTHCHECK"):
            path = _path_from_url(line)
            if path:
                found.append(path)
    return found


def compose_probes() -> list[str]:
    """Every service healthcheck `test` in the compose file that probes HTTP."""
    compose = yaml.safe_load((DEPLOYMENT / "docker-compose.yml").read_text(encoding="utf-8"))
    found = []
    for service in (compose.get("services") or {}).values():
        test = ((service or {}).get("healthcheck") or {}).get("test")
        if not test:
            continue
        parts = test if isinstance(test, list) else [test]
        for part in parts:
            path = _path_from_url(str(part))
            if path:
                found.append(path)
    return found


def kubernetes_probes() -> list[str]:
    """Only httpGet paths declared under a `probes:` block."""
    manifest = yaml.safe_load((DEPLOYMENT / "azure-deploy.yml").read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "probes" and isinstance(value, list):
                    for probe in value:
                        path = ((probe or {}).get("httpGet") or {}).get("path")
                        if path:
                            found.append(path)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(manifest)
    return found


def test_the_dockerfile_healthcheck_names_a_route_that_exists(flask_app):
    probed = dockerfile_probes()
    assert probed, "the Dockerfile no longer declares an HTTP HEALTHCHECK"
    for path in probed:
        assert path in _registered_paths(flask_app), (
            f"HEALTHCHECK probes {path}, which is not a route"
        )


def test_the_compose_healthcheck_names_a_route_that_exists(flask_app):
    probed = compose_probes()
    assert probed, "no compose service declares an HTTP healthcheck"
    for path in probed:
        assert path in _registered_paths(flask_app), f"compose probes {path}, which is not a route"


def test_the_kubernetes_probes_name_routes_that_exist(flask_app):
    """A readiness probe pointing at a route that does not exist means the pod
    never becomes ready, and the deployment silently serves nothing."""
    probed = kubernetes_probes()
    assert probed, "the manifest no longer declares probes"
    for path in probed:
        assert path in _registered_paths(flask_app), f"probe targets {path}, which is not a route"


def test_every_probe_url_actually_returns_success(client):
    """Existing as a route is not enough — the probe has to pass. This is the
    check that would have caught the SQLAlchemy 2.0 breakage directly."""
    probed = set(dockerfile_probes()) | set(compose_probes()) | set(kubernetes_probes())
    assert probed, "no probe URLs found in any deployment file"

    for path in sorted(probed):
        response = client.get(path)
        assert response.status_code == 200, (
            f"{path} is probed by deployment config but returns "
            f"{response.status_code}: {response.get_data(as_text=True)[:200]}"
        )


def test_the_readiness_probe_tolerates_a_slow_check():
    """Readiness takes a connection from the same pool that serves requests, so
    a load spike makes it slow rather than false. Kubernetes defaults
    timeoutSeconds to 1 and failureThreshold to 3; without an explicit, larger
    timeout one slow check pulls every pod out of service at once and deepens
    the spike it was reporting."""
    manifest = yaml.safe_load((DEPLOYMENT / "azure-deploy.yml").read_text(encoding="utf-8"))
    probes = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "probes" and isinstance(value, list):
                    probes.extend(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(manifest)
    readiness = [p for p in probes if p.get("type") == "Readiness"]
    assert readiness, "no readiness probe declared"

    for probe in readiness:
        assert probe.get("timeoutSeconds", 1) > 1, (
            "readiness probe relies on the 1s default timeout while the check "
            "waits on a connection pool"
        )
        assert probe.get("failureThreshold", 3) > 1, (
            "one slow readiness check should not remove the pod from service"
        )


# ── the probes are unauthenticated, so they must not describe the failure ──


def test_a_database_failure_tells_an_anonymous_caller_nothing_useful(client):
    """These endpoints cannot require a session — a container runtime probing
    them holds none. So the error body reaches anybody who can reach the port.

    A SQLAlchemy OperationalError names the host, address, port, database and
    user it failed to connect to. Echoing str(exc) put all of that in front of
    an unauthenticated caller. It was harmless only while the check was broken
    and every failure produced the same AttributeError text.
    """
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    failure = OperationalError(
        "SELECT 1",
        {},
        Exception(
            'connection to server at "db.internal" (10.0.0.5), port 5432 failed: '
            'FATAL: password authentication failed for user "appuser"'
        ),
    )
    secrets = ("db.internal", "10.0.0.5", "appuser", "5432", "password authentication")

    with patch("monitoring.health_checks._database_is_reachable", side_effect=failure):
        for path in ("/health/health", "/health/health/readiness", "/health/health/detailed"):
            body = client.get(path).get_data(as_text=True)
            leaked = [secret for secret in secrets if secret in body]
            assert not leaked, f"{path} disclosed {leaked} to an anonymous caller: {body[:300]}"


def test_a_failing_probe_still_reports_the_right_status(client):
    """Withholding the detail must not cost the signal the probe exists for."""
    from unittest.mock import patch

    with patch("monitoring.health_checks._database_is_reachable", side_effect=RuntimeError("x")):
        health = client.get("/health/health")
        assert health.status_code == 503
        assert health.get_json()["status"] == "unhealthy"

        readiness = client.get("/health/health/readiness")
        assert readiness.status_code == 503
        assert readiness.get_json()["status"] == "not_ready"

        # Liveness deliberately does not touch the database: a pod that cannot
        # reach Postgres should leave the rotation, not be killed and restarted
        # into the same outage.
        assert client.get("/health/health/liveness").status_code == 200
