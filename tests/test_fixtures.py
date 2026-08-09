"""Integrity of the vendored binary fixtures.

These checks need no optional dependency, so unlike ``tests/test_mpp.py`` they
run on every Python version in the matrix. That matters most for the one thing
a text-oriented toolchain gets wrong silently: a binary file committed from
Windows without a ``.gitattributes`` entry can have its line endings rewritten,
and a corrupted ``.mpp`` would not fail loudly — MPXJ would simply refuse it,
and the tests that depend on it would skip or error for the wrong reason.
"""

import hashlib
from pathlib import Path

DATA = Path(__file__).parent / "data"

EXAMPLE_MPP = DATA / "example.mpp"
EXAMPLE_MPP_SHA256 = "f3c482cc1d9a05ddd55b245682f8fc3a5c287758bffbf913235e225538333f2e"
EXAMPLE_MPP_BYTES = 209_920

# The OLE2 compound document signature. A real .mpp is a Microsoft structured
# storage file, not XML — this is what distinguishes it from every other format
# the suite handles.
OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def test_the_example_mpp_is_byte_for_byte_what_was_vendored():
    data = EXAMPLE_MPP.read_bytes()
    assert len(data) == EXAMPLE_MPP_BYTES
    assert hashlib.sha256(data).hexdigest() == EXAMPLE_MPP_SHA256


def test_the_example_mpp_is_still_a_binary_ole2_document():
    """Fails if the file was checked out through a line-ending filter."""
    assert EXAMPLE_MPP.read_bytes()[:8] == OLE2_MAGIC


def test_binary_fixtures_are_protected_from_line_ending_translation():
    """The .gitattributes entry is the actual fix; this stops it being
    deleted as unused, which would only show up as an unrelated failure on
    somebody else's machine."""
    attributes = (Path(__file__).resolve().parent.parent / ".gitattributes").read_text(
        encoding="utf-8"
    )
    assert "*.mpp binary" in attributes
