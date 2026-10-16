import json
import re

import pytest

from classscribe.sessions.manager import SessionManager, safe_slug
from classscribe.sessions.models import Session, Status
from classscribe.storage import atomic_json, exclusive_lock


@pytest.mark.parametrize(
    "title", ["CON", "NUL", "COM1", "LPT9", "../Clase: caché?", "🎓", "", "a" * 500]
)
def test_safe_session_slug(title):
    slug = safe_slug(title)
    assert re.fullmatch(r"[a-z0-9-]+", slug)
    assert len(slug) <= 70
    assert slug.upper() not in {"CON", "NUL", "COM1", "LPT9"}


def test_unique_directory_and_serialization(tmp_path):
    manager = SessionManager(tmp_path)
    first_dir, first = manager.create("Clase", "Curso")
    second_dir, second = manager.create("Clase", "Curso")
    assert first_dir != second_dir and first.session_id != second.session_id
    assert manager.load(first_dir) == first
    assert manager.find(first.session_id) == (first_dir, first)
    assert manager.find(second_dir.name) == (second_dir, second)
    raw = json.loads((first_dir / "session.json").read_text())
    assert raw["schema_version"] == 1
    assert raw["status"] == "created"
    assert "hostname" not in raw
    with pytest.raises(ValueError):
        manager.find("../missing")


def test_transitions(tmp_path):
    _, session = SessionManager(tmp_path).create("Clase")
    with pytest.raises(ValueError):
        session.transition(Status.COMPLETED)
    for state in (
        Status.RECORDING,
        Status.RECORDED,
        Status.TRANSCRIBING,
        Status.COMPLETED,
        Status.TRANSCRIBING,
        Status.FAILED,
        Status.TRANSCRIBING,
    ):
        session.transition(state)
        assert session.status == state


def test_importing_transitions_and_legacy_session_compatibility(tmp_path):
    manager = SessionManager(tmp_path)
    _, imported = manager.create("YouTube Lecture")
    with pytest.raises(ValueError):
        imported.transition(Status.RECORDED)
    imported.transition(Status.IMPORTING)
    assert imported.status == Status.IMPORTING
    with pytest.raises(ValueError):
        imported.transition(Status.TRANSCRIBING)
    imported.transition(Status.RECORDED)
    assert imported.status == Status.RECORDED

    _, failed_import = manager.create("Failed YouTube")
    failed_import.transition(Status.IMPORTING)
    failed_import.transition(Status.FAILED)
    assert failed_import.status == Status.FAILED

    # Legacy schema v1 session JSON without source_kind/youtube/importing fields still loads.
    legacy_payload = {
        "session_id": "0123456789abcdef0123456789abcdef",
        "title": "Legacy Class",
        "course": "History",
        "created_at": "2026-10-15T12:00:00+00:00",
        "platform": "Windows-11",
        "schema_version": 1,
        "status": "recorded",
        "recording_finalized": True,
    }
    legacy_session = Session.from_dict(legacy_payload)
    assert legacy_session.status == Status.RECORDED
    assert legacy_session.source_kind == "recording"
    assert legacy_session.youtube is None


def test_schema_version_rejected():
    with pytest.raises(ValueError, match="schema"):
        Session.from_dict({"schema_version": 99})


def test_unsafe_identity_rejected(tmp_path):
    _, session = SessionManager(tmp_path).create("Clase")
    metadata = session.to_dict()
    metadata["session_id"] = "../../outside"
    with pytest.raises(ValueError):
        Session.from_dict(metadata)


def test_blank_title_rejected(tmp_path):
    with pytest.raises(ValueError):
        SessionManager(tmp_path).create("   ")


def test_lock_exclusion_and_release(tmp_path):
    with (
        exclusive_lock(tmp_path),
        pytest.raises(RuntimeError, match="busy"),
        exclusive_lock(tmp_path),
    ):
        pass
    assert not (tmp_path / ".operation.lock").exists()


def test_atomic_write_preserves_old_on_failure(tmp_path):
    path = tmp_path / "data.json"
    atomic_json(path, {"old": True})
    with pytest.raises(TypeError):
        atomic_json(path, {"bad": object()})
    assert json.loads(path.read_text()) == {"old": True}
    assert list(tmp_path.iterdir()) == [path]


def test_one_corrupt_session_does_not_hide_other_sessions(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Valid")
    broken, _ = manager.create("Broken")
    (broken / "session.json").write_text("{unfinished")
    assert manager.find(session.session_id) == (directory, session)
