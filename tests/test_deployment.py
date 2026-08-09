"""The Dockerfile must survive a base image bump.

The production stage used to copy `/usr/local/lib/python3.11/site-packages` by
absolute path while the two `FROM` lines named the version separately. An
automated update bumped the `FROM` lines, the copy kept pointing at a directory
the new image does not have, and the build failed — thirty lines away from the
change, on a path nobody thought of as a version declaration.

These tests fail on the duplication rather than on the eventual broken build.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "deployment" / "Dockerfile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Matches 3.11, 3.13 and so on — but not a bare "3" or a package pin like
# "flask>=3.1.2", which is why the surrounding context is checked per use.
PYTHON_MINOR = re.compile(r"python:?(\d+\.\d+)")


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _base_image_versions() -> list[str]:
    return [
        match.group(1)
        for line in _dockerfile().splitlines()
        if line.startswith("FROM ")
        for match in [PYTHON_MINOR.search(line)]
        if match
    ]


def test_both_stages_name_the_same_python_version():
    versions = _base_image_versions()
    assert len(versions) == 2, f"expected two FROM lines naming Python, found {versions}"
    assert versions[0] == versions[1], f"builder and production disagree: {versions}"


def test_the_python_version_appears_only_on_the_from_lines():
    """The regression itself: a version buried in a COPY path is a second
    declaration that no bump will remember to update."""
    offenders = [
        line.strip()
        for line in _dockerfile().splitlines()
        if not line.startswith("FROM ")
        and not line.lstrip().startswith("#")
        and PYTHON_MINOR.search(line)
    ]
    assert not offenders, "Python version named outside a FROM line: " + "; ".join(offenders)


def test_dependencies_are_copied_from_a_path_with_no_version_in_it():
    assert "COPY --from=builder /opt/venv /opt/venv" in _dockerfile()


def test_ci_tests_the_python_version_the_image_ships():
    """Shipping a Python that no test job runs means production is the first
    place an incompatibility shows up."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    tested = {str(v) for v in workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]}

    shipped = _base_image_versions()[0]
    assert shipped in tested, (
        f"the image ships Python {shipped}, but CI only tests {sorted(tested)}"
    )
