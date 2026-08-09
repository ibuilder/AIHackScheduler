"""Execute the MPXJ code path, which nothing had ever run.

``services.schedule_io.read_mpp`` and ``_from_mpxj`` were written against the
MPXJ API and committed without once being called: MPXJ is a Java library
reached through JPype, and no environment here had a JVM. Code that has never
run is not known to work, so `_from_mpxj` even carried a
``pragma: no cover`` admitting it.

These tests need the ``mpp`` extra and a JVM, and skip without them. CI installs
both. The trick that makes this checkable at all is that MPXJ's
``UniversalProjectReader`` reads MSPDI XML as happily as binary ``.mpp`` — so
the same file can be put through MPXJ and through this project's own pure-Python
reader, and the two results compared. Nobody has to produce a ``.mpp``, and a
disagreement means one of the two readers is wrong.
"""

import pytest

from core.mspdi import read_mspdi
from tests.test_mspdi import SAMPLE_MSPDI

mpxj = pytest.importorskip("mpxj", reason="needs the mpp extra: pip install -e '.[mpp]'")
pytest.importorskip("jpype", reason="needs the mpp extra: pip install -e '.[mpp]'")

pytestmark = pytest.mark.mpp


@pytest.fixture(scope="module")
def via_mpxj():
    """The sample schedule, read by MPXJ through the real JVM bridge."""
    from services.schedule_io import read_mpp

    return read_mpp(SAMPLE_MSPDI.encode("utf-8"), "sample.xml")


@pytest.fixture(scope="module")
def via_python():
    """The same file, read by this project's own reader."""
    return read_mspdi(SAMPLE_MSPDI)


def test_the_jvm_bridge_returns_a_schedule(via_mpxj):
    """The baseline claim: this function runs at all."""
    assert via_mpxj.source_format == "mpp"
    assert via_mpxj.activities


def test_both_readers_find_the_same_activities(via_mpxj, via_python):
    assert {a.name for a in via_mpxj.activities} == {a.name for a in via_python.activities}


def test_both_readers_agree_on_durations(via_mpxj, via_python):
    """MPXJ reports durations in its own units, so an ISO 8601 duration
    misparsed by either side shows up here as a mismatch."""
    mine = {a.name: round(a.duration, 2) for a in via_python.activities}
    theirs = {a.name: round(a.duration, 2) for a in via_mpxj.activities}
    assert theirs == mine


def test_both_readers_agree_on_the_relationships(via_mpxj, via_python):
    """The link type codes are not alphabetical — 0=FF, 1=FS, 2=SF, 3=SS — so
    a table copied from intuition rather than the spec disagrees with MPXJ."""

    def edges(schedule):
        by_id = {a.id: a.name for a in schedule.activities}
        return {
            (by_id.get(r.predecessor_id), by_id.get(r.successor_id), r.type)
            for r in schedule.relationships
        }

    assert edges(via_mpxj) == edges(via_python)


def test_a_file_mpxj_cannot_parse_raises_a_clear_error():
    from services.schedule_io import ImportError_, read_mpp

    with pytest.raises(ImportError_):
        read_mpp(b"this is not a project file at all", "junk.mpp")
