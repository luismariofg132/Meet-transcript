import subprocess
import sys

import pytest
from conftest import FakeBackend

from classscribe.audio.recorder import record_session
from classscribe.cli import commands
from classscribe.config import Settings, load_settings
from classscribe.sessions.models import Status


def test_config_precedence(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('device = "cpu"\nmodel = "medium"\nmicrophone = false\n', encoding="utf-8")
    args = commands.parser().parse_args(
        ["--config", str(path), "record", "--title", "Clase", "--device", "cuda", "--microphone"]
    )
    settings = commands.settings_for(args)
    assert settings.device == "cuda"
    assert settings.model == "medium"
    assert settings.microphone
    assert load_settings(None, {}).model == "small"


@pytest.mark.parametrize(
    "content",
    [
        "unknown = true",
        'model = "giant"',
        'device = "vulkan"',
        'microphone = "false"',
        "offline = 1",
        "language = 123",
        "models_dir = 42",
    ],
)
def test_invalid_config(tmp_path, content):
    path = tmp_path / "settings.toml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_settings(path, {})


@pytest.mark.parametrize(
    "argv,command",
    [
        (["doctor"], "doctor"),
        (["doctor", "--device", "cuda", "--model", "tiny"], "doctor"),
        (["devices"], "devices"),
        (["record", "--title", "Clase", "--no-microphone"], "record"),
        (["record", "--title", "Clase", "--course", "Arq", "--transcribe"], "record"),
        (
            ["transcribe", "abc123", "--model", "medium", "--device", "cpu", "--language", "es"],
            "transcribe",
        ),
    ],
)
def test_cli_examples_parse(argv, command):
    assert commands.parser().parse_args(argv).command == command


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_duration(value):
    with pytest.raises(SystemExit):
        commands.parser().parse_args(["record", "--title", "Clase", "--duration", value])


def test_record_plus_transcribe_is_strictly_sequential(tmp_path, monkeypatch):
    from classscribe.transcription import service

    monkeypatch.chdir(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr(commands, "WasapiBackend", lambda: backend)

    def recording(manager, directory, session, hardware, devices, **kwargs):
        def interrupt(_):
            assert "transcribe" not in backend.events
            raise KeyboardInterrupt

        return record_session(
            manager, directory, session, hardware, devices, clock=lambda: 100, wait=interrupt
        )

    def transcription(manager, directory, session, settings):
        assert all(stream.closed for stream in backend.streams)
        assert backend.events[-1] == "backend:close"
        assert manager.load(directory).status == Status.RECORDED
        assert session.recording_finalized
        backend.events.append("transcribe")
        return tmp_path / "result"

    monkeypatch.setattr(commands, "record_session", recording)
    monkeypatch.setattr(service, "transcribe_session", transcription)
    assert commands.main(["record", "--title", "Clase", "--transcribe", "--no-microphone"]) == 0
    assert backend.events[-1] == "transcribe"


def test_record_failure_does_not_schedule_transcription(tmp_path, monkeypatch):
    from classscribe.transcription import service

    monkeypatch.chdir(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr(commands, "WasapiBackend", lambda: backend)

    def failure(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(commands, "record_session", failure)
    monkeypatch.setattr(
        service, "transcribe_session", lambda *a: pytest.fail("Unexpected transcription")
    )
    assert commands.main(["record", "--title", "Clase", "--transcribe"]) == 1
    assert backend.events[-1] == "backend:close"


def test_recording_import_does_not_import_whisper():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import classscribe.cli.commands; "
            "assert 'faster_whisper' not in sys.modules; "
            "assert 'ctranslate2' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_device_listing_marks_defaults(monkeypatch, capsys):
    monkeypatch.setattr(commands, "WasapiBackend", FakeBackend)
    commands.list_devices()
    output = capsys.readouterr().out
    assert "[10] Speakers [Loopback] (default)" in output
    assert "MICROPHONES" in output


def test_microphone_selector_overrides_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr(commands, "WasapiBackend", lambda: backend)
    selected = []

    def capture(manager, directory, session, backend, devices, **kwargs):
        selected.extend(devices)

    monkeypatch.setattr(commands, "record_session", capture)
    args = commands.parser().parse_args(["record", "--title", "Clase", "--microphone-device", "4"])
    commands.run_record(args, Settings(microphone=False))
    assert len(selected) == 2
