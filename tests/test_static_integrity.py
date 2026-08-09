"""Calls to methods that do not exist.

``AzureAIPredictiveAnalytics.optimize_resource_allocation`` and
``generate_project_insights`` each called a chain of private helpers, nine of
which were never written. Both raised ``AttributeError`` on their first line of
real work, and the blueprint caught it and returned a generic 500, so the
endpoints looked merely unlucky rather than impossible. They are implemented
now; this check is what stops the shape recurring.

Python does not resolve attributes until the line runs, so nothing but reaching
the line reveals this. Reaching the line is exactly what does not happen for
code with no test and no user. This walks the AST instead.

The one thing it cannot see is a method attached at import time
(``SomeClass._helper = _helper``). Two of the original eleven were bound that
way and were reported as missing when they were not — so treat a finding as a
lead, and confirm with ``hasattr`` before recording it below.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "migrations",
    "tests",
    # Build artefacts hold a verbatim copy of the source tree. `python -m build`
    # writes build/lib/<package>/..., and scanning that reported every known gap
    # a second time under a path KNOWN_MISSING does not name — so packaging the
    # project and then running the suite failed it. The CI package job uses a
    # separate checkout, so this only ever bit locally, which is worse.
    "build",
    "dist",
    ".eggs",
    ".tox",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
}

# Deliberately empty. The eleven helpers behind
# optimize_resource_allocation and generate_project_insights are implemented,
# so any entry here now would be a fresh gap rather than a recorded one.
#
# Two of the eleven were never missing: they were attached to the class at
# import time with `AzureAIPredictiveAnalytics._x = _x`, which no AST can see.
# That is a false positive this check cannot avoid in general -- so if an entry
# ever needs adding, confirm with hasattr() before believing it.
KNOWN_MISSING: dict[tuple[str, str], set[str]] = {}


def _python_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if not any(part in SKIP_DIRS for part in path.parts):
            yield path


def _own_nodes(cls: ast.ClassDef):
    """Every node belonging to ``cls``, stopping at a nested class boundary.

    ``ast.walk`` descends into nested classes, which charged an inner class's
    ``self.helper()`` to the outer one — where ``helper`` is quite correctly not
    defined. That reported a false missing method for any nested class.
    """
    for statement in cls.body:
        if isinstance(statement, ast.ClassDef):
            continue  # analysed separately, on its own terms
        yield from ast.walk(statement)


def _names_defined_by(cls: ast.ClassDef) -> set[str]:
    """Everything ``self.x`` could legitimately resolve to on this class."""
    defined = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    # Names bound at class scope. `handler = _module_level_function` and
    # `run = staticmethod(...)` are ordinary ways to attach a callable, and
    # counting only `def` reported them as missing.
    for statement in cls.body:
        if isinstance(statement, ast.Assign):
            defined |= {t.id for t in statement.targets if isinstance(t, ast.Name)}
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            defined.add(statement.target.id)

    # Attributes assigned on self anywhere in the class, which may be callables.
    for node in _own_nodes(cls):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and isinstance(node.ctx, ast.Store)
        ):
            defined.add(node.attr)

    return defined


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
            defined |= _names_defined_by(classes[owner])

        called = {
            n.func.attr
            for n in _own_nodes(node)
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
        path = REPO_ROOT / relative
        assert path.is_file(), f"KNOWN_MISSING names {relative}, which no longer exists"

        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Distinguish "the methods got written" from "the class went away".
        # Inferring one from the absence of the other told the reader to go
        # looking for eleven implementations that a rename had not produced.
        classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        assert class_name in classes, (
            f"KNOWN_MISSING names {relative}::{class_name}, which no longer exists "
            f"— it was renamed or removed, so update the entry rather than the code"
        )

        fixed = allowed - _missing_methods(tree).get(class_name, set())
        assert not fixed, (
            f"{relative}::{class_name} now defines {sorted(fixed)} — remove them from KNOWN_MISSING"
        )


# ── SQLAlchemy legacy API ────────────────────────────────────────────────


def test_nothing_uses_the_legacy_query_get():
    """``Model.query.get(id)`` is legacy in SQLAlchemy 2.0 and removed in 2.1.

    The bound in pyproject is ``sqlalchemy<3``, so 2.1 arrives as a Dependabot
    proposal and takes 22 call sites with it — on code nobody touched. This is
    the third instance of that shape in this repository, after
    ``db.engine.execute`` (removed in 2.0, and it had been failing every health
    check since) and MPXJ renaming its Java package. Use
    ``db.session.get(Model, id)``.

    ``get_or_404`` is Flask-SQLAlchemy's own and is not affected.
    """
    import re

    offenders = []
    # Matches `Something.query.get(` but not `.query.get_or_404(`.
    pattern = re.compile(r"\.query\.get\(")

    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                offenders.append(f"{relative}:{number}")

    assert not offenders, (
        "Query.get() is removed in SQLAlchemy 2.1; use db.session.get(Model, id): "
        + ", ".join(offenders)
    )
