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
from tests.test_fixtures import EXAMPLE_MPP
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


# ── a genuine binary .mpp ────────────────────────────────────────────────
#
# Everything above cross-checks MPXJ against this project's own reader using
# MSPDI XML, which both can read. That covers the translation in _from_mpxj,
# but not the binary parser — and binary .mpp is the one format here that no
# test can generate, because nothing except Microsoft Project can write it.
#
# So tests/data/example.mpp is vendored: a real OLE2 compound document written
# by MS Project 2010, MIT licensed, from the author of MPXJ. See
# tests/data/README.md for provenance.

# The fixture's integrity is checked in tests/test_fixtures.py, which has no
# optional dependency and so runs on every Python version — a corrupted file
# would otherwise surface here as MPXJ refusing to read it, which reads like a
# bug in the reader rather than in the checkout.


@pytest.fixture(scope="module")
def real_mpp():
    from services.schedule_io import read_mpp

    return read_mpp(EXAMPLE_MPP.read_bytes(), "example.mpp")


def test_a_real_binary_mpp_is_read(real_mpp):
    """The claim this whole fixture exists to support: the binary path works
    on bytes that came out of Microsoft Project."""
    print(
        f"\n  name={real_mpp.name!r}  activities={len(real_mpp.activities)}  "
        f"relationships={len(real_mpp.relationships)}  warnings={len(real_mpp.warnings)}"
    )
    for activity in real_mpp.activities[:10]:
        print(f"    {activity.id:>4}  {activity.duration:>6.2f}d  {activity.name}")

    assert real_mpp.source_format == "mpp"
    assert real_mpp.activities, "read a real .mpp but found no activities"


def test_every_activity_has_a_name_and_a_usable_duration(real_mpp):
    for activity in real_mpp.activities:
        assert activity.name.strip(), f"activity {activity.id} has no name"
        assert activity.duration >= 0, f"activity {activity.id} has a negative duration"


def test_no_relationship_dangles(real_mpp):
    """A predecessor the reader dropped would leave an edge pointing nowhere,
    and CPM would raise on it rather than schedule."""
    known = {a.id for a in real_mpp.activities}
    for relation in real_mpp.relationships:
        assert relation.predecessor_id in known, f"dangling predecessor {relation.predecessor_id}"
        assert relation.successor_id in known, f"dangling successor {relation.successor_id}"


def test_nothing_in_the_file_was_left_unmapped(real_mpp):
    """Unrecognised relationship types are recorded rather than assumed, so an
    empty warnings list means the whole file was understood."""
    assert real_mpp.warnings == []


def test_a_real_mpp_schedules_end_to_end(real_mpp):
    """Parsing is not the point — the result has to be usable. This takes the
    imported schedule through the CPM engine and gets a critical path out."""
    from core.cpm import calculate_cpm

    activities, relationships = real_mpp.to_cpm()
    result = calculate_cpm(activities, relationships)

    assert result.duration > 0, "a real schedule computed a zero-length project"
    critical = [a for a in result.activities.values() if a.is_critical]
    assert critical, "no critical path in a real schedule"
    print(
        f"\n  project duration={result.duration} working days, "
        f"{len(critical)}/{len(activities)} activities critical"
    )
