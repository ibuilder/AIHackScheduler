"""Compatibility shim for the retired ``/management`` admin surface.

Administration used to be split across two blueprints — ``admin`` at ``/admin``
and ``user_management`` at ``/management`` — implementing the same three views
against the same templates, and redirecting into each other. They are merged
into :mod:`blueprints.admin`.

This keeps ``/management/*`` resolving so existing links, bookmarks and any
integration that hardcoded a path continue to work. Every route here is a
permanent redirect to its ``/admin`` equivalent and nothing else; the real
implementations live in one place now.

Delete this module once the redirects stop being hit.
"""

from flask import Blueprint, redirect, url_for

user_management_bp = Blueprint("user_management", __name__)

# Retired path -> the endpoint that replaced it. Kept as data so
# tests/test_admin.py can assert every entry still resolves.
REDIRECTS = {
    "/users": "admin.manage_users",
    "/users/create": "admin.create_user",
    "/company/settings": "admin.company_settings",
    "/audit-logs": "admin.audit_logs",
    "/system-status": "admin.system_status",
}

REDIRECTS_WITH_USER = {
    "/users/<int:user_id>/edit": "admin.edit_user",
    "/users/<int:user_id>/deactivate": "admin.deactivate_user",
    "/users/<int:user_id>/activate": "admin.activate_user",
}


def _register():
    """Build one redirect view per retired path.

    308 rather than 302: a permanent redirect preserves the method and body, so
    a POST to a retired path still arrives at the new one as a POST. A 302
    would silently turn it into a GET and lose the form.
    """
    for path, endpoint in REDIRECTS.items():

        def view(_endpoint=endpoint):
            return redirect(url_for(_endpoint), code=308)

        view.__name__ = f"redirect_{endpoint.split('.')[-1]}"
        user_management_bp.add_url_rule(path, view_func=view, methods=["GET", "POST"])

    for path, endpoint in REDIRECTS_WITH_USER.items():

        def user_view(user_id, _endpoint=endpoint):
            return redirect(url_for(_endpoint, user_id=user_id), code=308)

        user_view.__name__ = f"redirect_{endpoint.split('.')[-1]}"
        user_management_bp.add_url_rule(path, view_func=user_view, methods=["GET", "POST"])


_register()

# The old module exported `admin_bp`; keep the name importable so nothing that
# still refers to it breaks on import.
admin_bp = user_management_bp
