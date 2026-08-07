"""Rate limiting and request hardening.

Limits are attached to the *real* view functions after the blueprints are
registered. The previous version declared throwaway routes at the same URLs as
the genuine endpoints (``/auth/login``, ``/api/<path:path>``), which shadowed
live routes without limiting anything.
"""

import logging

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# endpoint name -> limit string. Endpoint names are ``blueprint.function``.
ENDPOINT_LIMITS = {
    "auth.login": "10 per minute",
    "auth.register": "5 per hour",
    "projects.create_project": "30 per hour",
    "scheduling.update_task": "120 per minute",
    "azure.analyze_project": "20 per hour",
    "azure.ai_optimize": "20 per hour",
}

# Endpoint prefixes that get a shared API budget.
API_PREFIX_LIMIT = "300 per hour"
API_PREFIXES = ("analytics.", "project_mgmt.", "powerbi.", "azure_ai.")


def get_user_id():
    """Rate-limit key: the signed-in user, falling back to the client address."""
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return f"user:{current_user.id}"
    except Exception:  # outside a request context, or login not initialised
        pass
    return get_remote_address()


def setup_rate_limiting(app):
    """Attach limits to registered endpoints. Call after blueprints register."""
    storage_uri = app.config.get("RATELIMIT_STORAGE_URL") or app.config.get(
        "REDIS_URL", "memory://"
    )

    try:
        limiter = Limiter(
            get_user_id,
            app=app,
            storage_uri=storage_uri,
            default_limits=["1000 per hour"],
            headers_enabled=True,
        )
    except Exception as exc:
        # A missing or unreachable Redis must not take the application down.
        app.logger.warning(
            "Rate limit storage %s unavailable (%s); falling back to in-process memory. "
            "Memory storage is per-worker and does not hold across a restart.",
            storage_uri,
            exc,
        )
        limiter = Limiter(get_user_id, app=app, default_limits=["1000 per hour"])

    applied, missing = 0, []
    for endpoint, limit in ENDPOINT_LIMITS.items():
        view = app.view_functions.get(endpoint)
        if view is None:
            missing.append(endpoint)
            continue
        app.view_functions[endpoint] = limiter.limit(limit)(view)
        applied += 1

    for endpoint, view in list(app.view_functions.items()):
        if endpoint.startswith(API_PREFIXES) and endpoint not in ENDPOINT_LIMITS:
            app.view_functions[endpoint] = limiter.limit(API_PREFIX_LIMIT)(view)
            applied += 1

    if missing:
        app.logger.warning("Rate limits skipped for unknown endpoints: %s", ", ".join(missing))
    app.logger.info("Rate limiting applied to %d endpoints", applied)
    return limiter


class SecurityMiddleware:
    """Response hardening and request size limits.

    Content-Security-Policy is deliberately *not* set here — Flask-Talisman
    owns it in production, and setting it in two places produced conflicting
    headers whose effective policy depended on ordering.
    """

    def __init__(self, app):
        self.app = app
        self.setup_security_headers()
        self.setup_input_validation()

    def setup_security_headers(self):
        talisman_active = not self.app.config.get("DEBUG", False)

        @self.app.after_request
        def add_security_headers(response):
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
            )

            # In development Talisman is off, so supply a baseline CSP here.
            if not talisman_active:
                response.headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
                    "https://cdnjs.cloudflare.com; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
                    "https://cdnjs.cloudflare.com; "
                    "img-src 'self' data: https:; "
                    "font-src 'self' https://cdn.jsdelivr.net; "
                    "connect-src 'self';",
                )
            return response

    def setup_input_validation(self):
        """Reject oversized requests.

        The previous implementation also rejected any query string containing
        the substrings ``select``, ``update``, ``delete`` or ``script``. That
        blocked legitimate traffic — a project named "Selected Phase 2", a
        ``?sort=updated_at`` parameter — while providing no real protection,
        since every query in this codebase goes through SQLAlchemy's parameter
        binding. Input is validated at the point of use instead.
        """

        @self.app.before_request
        def validate_request_size():
            if request.path.startswith("/static/"):
                return None

            max_content_length = self.app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
            if request.content_length and request.content_length > max_content_length:
                logging.warning(
                    "Rejected oversized request: %s bytes from %s",
                    request.content_length,
                    get_remote_address(),
                )
                return "Request too large", 413
            return None
