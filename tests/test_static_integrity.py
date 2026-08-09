"""Calls to methods that do not exist.

``AzureAIPredictiveAnalytics.optimize_resource_allocation`` and
``generate_project_insights`` each call a chain of private helpers, eleven of
which were never written — and two of which sit at module scope taking ``self``,
having been dedented out of the class at some point. Both public methods raised
``AttributeError`` on their first line of real work, and the blueprint caught it
and returned a generic 500, so the endpoints looked merely unlucky rather than
impossible.

Python does not resolve attributes until the line runs, so nothing but reaching
the line reveals this. Reaching the line is exactly what does not happen for
code with no test and no user. This walks the AST instead.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "migrations", "tests"}

# The eleven helpers behind optimize_resource_allocation and
# generate_project_insights. Implementing them means designing a resource
# optimiser and a company analytics engine, which is a feature and not a fix —
# recorded here so the gap is explicit and so no *new* one can be added
# unnoticed. The two marked below exist at module scope taking `self`.
KNOWN_MISSING = {
    ("azure_ai/predictive_analytics.py", "AzureAIPredictiveAnalytics"): {
        "_ai_company_insights",  # at module scope, takes self
        "_ai_resource_optimization",
        "_analyze_current_resources",
        "_analyze_trends",
        "_calculate_cost_impact",
        "_calculate_efficiency_gains",
        "_gather_historical_data",  # at module scope, takes self
        "_industry_benchmarking",
        "_predict_future_performance",
        "_prioritize_optimizations",
        "_strategic_recommendations",
    },
}


def _python_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if not any(part in SKIP_DIRS for part in path.parts):
            yield path


def _missing_methods(tree: ast.Module) -> dict[str, set[str]]:
    """Per class, the names called on ``self`` that the class never defines."""
    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    missing = {}

    for name, node in classes.items():
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        # Only classes whose bases are all defined in this same file, otherwise
        # an inherited method is indistinguishable from a missing one.
        if any(not isinstance(b, ast.Name) for b in node.bases) or any(
            b not in classes for b in bases
        ):
            continue

        defined = set()
        for owner in [name, *bases]:
            owner_node = classes[owner]
            defined |= {
                n.name
                for n in owner_node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            # Attributes assigned on self, which may be callables.
            for n in ast.walk(owner_node):
                if (
                    isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id == "self"
                    and isinstance(n.ctx, ast.Store)
                ):
                    defined.add(n.attr)

        called = {
            n.func.attr
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "self"
        }

        if called - defined:
            missing[name] = called - defined

    return missing


def test_no_class_calls_a_method_it_does_not_define():
    unexpected = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - a parse error is its own bug
            raise AssertionError(f"{path} does not parse: {exc}") from exc

        relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for class_name, names in _missing_methods(tree).items():
            allowed = KNOWN_MISSING.get((relative, class_name), set())
            for name in sorted(names - allowed):
                unexpected.append(f"{relative}::{class_name}.{name}")

    assert not unexpected, (
        "These call methods that do not exist and will raise AttributeError: "
        + (", ".join(unexpected))
    )


def test_the_known_gaps_are_still_real():
    """If someone implements one, this fails and the entry must be removed —
    otherwise the allowlist quietly grows stale and starts hiding new breakage."""
    for (relative, class_name), allowed in KNOWN_MISSING.items():
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        still_missing = _missing_methods(tree).get(class_name, set())
        fixed = allowed - still_missing
        assert not fixed, (
            f"{relative}::{class_name} now defines {sorted(fixed)} — remove them from KNOWN_MISSING"
        )
