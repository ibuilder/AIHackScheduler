"""Helpers for optional third-party integrations.

The platform's scheduling engine is self-contained. Azure AI, Power BI,
Microsoft Fabric, Stripe and Celery are all enhancements, and none of them
should be able to stop the application from starting.

Before this existed, ``services/azure_ai.py`` imported ``openai`` at module
scope and the Azure blueprint imported that service at module scope, so a
missing optional package raised ``ModuleNotFoundError`` during ``create_app``
and the whole platform failed to boot.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class IntegrationUnavailable(RuntimeError):
    """Raised when a feature is requested but its integration is not usable."""

    def __init__(self, integration: str, reason: str):
        self.integration = integration
        self.reason = reason
        super().__init__(f"{integration} is unavailable: {reason}")

    def as_response(self) -> dict:
        """A JSON body describing the gap, for API callers."""
        return {
            "success": False,
            "error": str(self),
            "integration": self.integration,
            "remediation": self.reason,
        }


def optional_import(module_name: str, *, feature: str) -> Any | None:
    """Import a module if it is installed, otherwise return ``None``."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        logger.info(
            "%s is disabled: the %r package is not installed. "
            'Install it with: pip install -e ".[integrations]"',
            feature,
            module_name,
        )
        return None


def require(module_name: str, *, feature: str) -> Any:
    """Import a module or raise :class:`IntegrationUnavailable`."""
    module = optional_import(module_name, feature=feature)
    if module is None:
        raise IntegrationUnavailable(
            feature,
            f'the {module_name!r} package is not installed (pip install -e ".[integrations]")',
        )
    return module


def require_settings(feature: str, **settings: Any) -> None:
    """Raise unless every named setting has a value."""
    missing = sorted(name for name, value in settings.items() if not value)
    if missing:
        raise IntegrationUnavailable(feature, f"missing configuration: {', '.join(missing)}")
