"""Import and export against the database, and the API around it."""

import io

import pytest

from extensions import db
from models import Project, Task, TaskDependency
from services.schedule_io import (
    ImportError_,
    capabilities,
    detect_format,
    export_project,
    import_into_project,
    read_schedule_file,
    serialise,
)
from tests.test_mspdi import SAMPLE_MSPDI
from tests.test_xer import SAMPLE_XER

# ── format detection and capabilities ────────────────────────────────────


def test_format_detection():
    assert detect_format("schedule.xer") == "xer"
    assert detect_format("SCHEDULE.XER") == "xer"
    assert detect_format("plan.xml") == "mspdi"
    assert detect_format("plan.mpp") == "mpp"


def test_unknown_extension_is_rejected():
    with pytest.raises(ImportError_, match="Unsupported file type"):
        detect_format("schedule.pdf")


def test_capabilities_state_that_mpp_cannot_be_written():
    """Not a limitation of this project — no library can write the binary
    format, so the UI must not offer it."""
    caps = capabilities()

    assert caps["write"]["xer"] is True
    assert caps["write"]["mspdi"] is True
    assert caps["write"]["mpp"] is False
    assert "cannot be written" in caps["notes"]["mpp_write"]


def test_reading_mpp_without_mpxj_gives_a_clear_message():
    from services.optional import IntegrationUnavailable

    if capabilities()["read"]["mpp"]:
        pytest.skip("MPXJ is installed in this environment")

    with pytest.raises(IntegrationUnavailable, match="mpxj"):
        read_schedule_file(b"\xd0\xcf\x11\xe0", "plan.mpp")


# ── decoding ─────────────────────────────────────────────────────────────


def test_a_windows_1252_xer_is_decoded():
    """P6 writes windows-1252; rejecting a file over one accented character
    would lose the whole schedule."""
    content = SAMPLE_XER.replace("Mobilise", "Mobilisé")
    schedule = read_schedule_file(content.encode("windows-1252"), "plan.xer")

    assert schedule.activity("T1").name == "Mobilisé"


def test_a_utf8_bom_is_stripped():
    schedule = read_schedule_file(SAMPLE_XER.encode("utf-8-sig"), "plan.xer")
    assert len(schedule.activities) == 5


def test_a_file_that_is_not_a_schedule_is_rejected():
    with pytest.raises(ImportError_):
        read_schedule_file(b"just some text", "plan.xer")


# ── importing into the database ──────────────────────────────────────────


@pytest.fixture
def imported(signed_in):
    _, _, user = signed_in
    schedule = read_schedule_file(SAMPLE_XER.encode(), "plan.xer")
    return import_into_project(schedule, user.company_id, user.id), user


def test_import_creates_a_project_with_its_tasks(imported):
    project, _ = imported
    tasks = Task.query.filter_by(project_id=project.id).all()

    assert project.name == "Northgate Tower Fit-Out"
    assert len(tasks) == 5


def test_import_preserves_relationship_types(imported):
    """The whole point: an SS tie must arrive as SS, not silently as FS."""
    project, _ = imported
    task_ids = {t.id for t in Task.query.filter_by(project_id=project.id).all()}
    links = TaskDependency.query.filter(TaskDependency.task_id.in_(task_ids)).all()
    types = {link.dependency_type for link in links}

    assert types == {"FS", "SS", "FF", "SF"}


def test_import_preserves_milestones_as_zero_duration(imported):
    project, _ = imported
    milestone = Task.query.filter_by(project_id=project.id, name="Structure complete").one()

    assert milestone.duration == 0


def test_import_uses_the_calendars_hours_per_day(imported):
    """The sample is a 10-hour calendar; 50 hours is 5 days, not 6."""
    project, _ = imported
    task = Task.query.filter_by(project_id=project.id, name="Mobilise").one()

    assert task.duration == 5


def test_import_carries_actuals_across(imported):
    from datetime import date

    project, _ = imported
    done = Task.query.filter_by(project_id=project.id, name="Mobilise").one()

    assert done.actual_start == date(2026, 9, 7)
    assert done.actual_finish == date(2026, 9, 11)
    assert done.is_complete


def test_importing_the_same_schedule_twice_does_not_collide(signed_in):
    """Successive revisions of one plan carry the same project code."""
    _, _, user = signed_in
    schedule = read_schedule_file(SAMPLE_XER.encode(), "plan.xer")

    first = import_into_project(schedule, user.company_id, user.id)
    second = import_into_project(schedule, user.company_id, user.id)

    assert first.project_number != second.project_number
    assert second.project_number.startswith("NGT-2026")


def test_two_companies_may_use_the_same_project_number(app_context):
    """project_number was globally unique, so a second tenant importing a
    schedule with the same code failed outright."""
    from datetime import date

    from models import Company

    a, b = Company(name="Alpha"), Company(name="Beta")
    db.session.add_all([a, b])
    db.session.flush()

    for company in (a, b):
        db.session.add(
            Project(
                name="Shared code",
                project_number="P-001",
                company_id=company.id,
                start_date=date(2026, 1, 5),
                end_date=date(2026, 6, 5),
            )
        )
    db.session.commit()

    assert Project.query.filter_by(project_number="P-001").count() == 2


def test_an_empty_schedule_is_refused(signed_in):
    from core.exchange import ExchangeSchedule

    _, _, user = signed_in
    with pytest.raises(ImportError_, match="no activities"):
        import_into_project(ExchangeSchedule(), user.company_id, user.id)


# ── exporting and round-tripping ─────────────────────────────────────────


def test_export_produces_both_formats(seeded):
    schedule = export_project(seeded.id)

    xer, xer_name, _ = serialise(schedule, "xer")
    xml, xml_name, mimetype = serialise(schedule, "mspdi")

    assert xer.startswith("ERMHDR\t")
    assert xer_name.endswith(".xer")
    assert xml.startswith('<?xml version="1.0"')
    assert xml_name.endswith(".xml")
    assert mimetype == "application/xml"


def test_mpp_is_not_an_export_option(seeded):
    schedule = export_project(seeded.id)

    with pytest.raises(ValueError, match="Unsupported export format"):
        serialise(schedule, "mpp")


@pytest.mark.parametrize("export_format,suffix", [("xer", ".xer"), ("mspdi", ".xml")])
def test_a_project_survives_export_and_reimport(seeded, signed_in, export_format, suffix):
    """The strongest check available: export, re-import, and confirm the
    computed schedule has not moved."""
    from services.schedule_analysis import analyse_project

    _, _, user = signed_in
    before = analyse_project(seeded.id)

    content, _, _ = serialise(export_project(seeded.id), export_format)
    reimported = import_into_project(
        read_schedule_file(content.encode(), f"round-trip{suffix}"),
        user.company_id,
        user.id,
        project_name=f"Round trip {export_format}",
    )
    after = analyse_project(reimported.id)

    assert after["project_duration_days"] == before["project_duration_days"]
    assert after["calculated_finish"] == before["calculated_finish"]
    assert len(after["critical_path"]) == len(before["critical_path"])
    assert len(after["activities"]) == len(before["activities"])


def test_export_of_a_missing_project_raises(app_context):
    with pytest.raises(LookupError):
        export_project(999999)


# ── the API ──────────────────────────────────────────────────────────────


def test_formats_endpoint_reports_capabilities(signed_in):
    client, _, _ = signed_in
    body = client.get("/api/schedule/formats").get_json()

    assert body["write"]["mpp"] is False
    assert body["read"]["xer"] is True


def test_upload_creates_a_project(signed_in):
    client, _, _ = signed_in
    response = client.post(
        "/api/schedule/import",
        data={"file": (io.BytesIO(SAMPLE_XER.encode()), "plan.xer")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["imported"]["activities"] == 5
    assert body["imported"]["relationship_types"] == {"FS": 1, "SS": 1, "FF": 1, "SF": 1}


def test_upload_surfaces_reader_warnings_rather_than_dropping_them(signed_in):
    client, _, _ = signed_in
    mangled = SAMPLE_XER.replace("PR_SS", "PR_XX")
    response = client.post(
        "/api/schedule/import",
        data={"file": (io.BytesIO(mangled.encode()), "plan.xer")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    assert any("PR_XX" in w for w in response.get_json()["warnings"])


def test_upload_with_no_file_is_rejected(signed_in):
    client, _, _ = signed_in
    response = client.post("/api/schedule/import", data={}, content_type="multipart/form-data")

    assert response.status_code == 400


def test_upload_of_an_empty_file_is_rejected(signed_in):
    client, _, _ = signed_in
    response = client.post(
        "/api/schedule/import",
        data={"file": (io.BytesIO(b""), "plan.xer")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400


def test_upload_of_an_unreadable_file_is_rejected(signed_in):
    client, _, _ = signed_in
    response = client.post(
        "/api/schedule/import",
        data={"file": (io.BytesIO(b"nonsense"), "plan.xer")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422


def test_upload_of_an_mspdi_file(signed_in):
    client, _, _ = signed_in
    response = client.post(
        "/api/schedule/import",
        data={"file": (io.BytesIO(SAMPLE_MSPDI.encode()), "plan.xml")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    assert response.get_json()["imported"]["activities"] == 4


def test_download_returns_an_attachment(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/export/xer")

    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.get_data(as_text=True).startswith("ERMHDR\t")


def test_download_as_mspdi(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/export/mspdi")

    assert response.status_code == 200
    assert response.mimetype == "application/xml"


def test_download_rejects_an_unknown_format(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/export/mpp")

    assert response.status_code == 400
    assert "Unsupported export format" in response.get_json()["error"]


def test_export_is_refused_for_another_tenants_project(signed_in, app_context):
    from datetime import date

    from models import Company

    client, _, _ = signed_in
    rival = Company(name="Rival Exporters")
    db.session.add(rival)
    db.session.flush()
    rival_project = Project(
        name="Confidential",
        company_id=rival.id,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 6, 5),
    )
    db.session.add(rival_project)
    db.session.commit()

    response = client.get(f"/api/schedule/projects/{rival_project.id}/export/xer")
    assert response.status_code == 404
