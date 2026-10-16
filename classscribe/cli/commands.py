import argparse
import json
import logging
import math
import sys
from pathlib import Path

from classscribe import __version__
from classscribe.application.recording import RecordingService
from classscribe.application.transcription import transcribe
from classscribe.application.youtube import YouTubeService
from classscribe.audio.devices import Device
from classscribe.audio.recorder import record_session
from classscribe.audio.wasapi import WasapiBackend
from classscribe.config import DEVICES, MODELS, Settings, load_settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session
from classscribe.storage import timestamp
from classscribe.youtube import YouTubeMetadata, YtDlpClient, import_youtube_session


def positive_seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Duration must be a positive number of seconds")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="classscribe", description="Record locally, transcribe afterwards"
    )
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument(
        "--config", type=Path, help="TOML settings (default: ./classscribe.toml if present)"
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="List WASAPI loopbacks and microphones")
    doctor = commands.add_parser(
        "doctor", help="Inspect setup; --device also runs actual inference"
    )
    doctor.add_argument("--json", action="store_true", help="Print structured diagnostic JSON")
    record = commands.add_parser(
        "record", help="Record until Ctrl+C; inference never runs during capture"
    )
    record.add_argument("--title", required=True)
    record.add_argument("--course", default="")
    record.add_argument("--output-device", help="Loopback ID or exact name from devices")
    record.add_argument("--microphone-device", help="Microphone ID or exact name from devices")
    record.add_argument("--microphone", action=argparse.BooleanOptionalAction, default=None)
    record.add_argument("--transcribe", action="store_true")
    record.add_argument("--duration", type=positive_seconds, help="Stop after this many seconds")
    youtube = commands.add_parser(
        "youtube", help="Import audio from a YouTube video URL into a local session"
    )
    youtube.add_argument("url", help="YouTube video URL")
    youtube.add_argument(
        "--title", default="", help="Override session title (default: video title)"
    )
    youtube.add_argument("--course", default="", help="Course name (default: channel/uploader)")
    youtube.add_argument(
        "--inspect",
        action="store_true",
        help="Inspect and print video metadata without downloading",
    )
    youtube.add_argument(
        "--transcribe", action="store_true", help="Transcribe after importing audio"
    )
    transcribe = commands.add_parser(
        "transcribe", help="Create a new transcription run for a session"
    )
    transcribe.add_argument("session_id", help="Full session ID or exact session directory name")
    for command in (record, youtube, transcribe, doctor):
        command.add_argument("--device", choices=DEVICES, default=None)
        command.add_argument("--model", choices=MODELS, default=None)
        command.add_argument("--language", default=None, help="Language code (default es), or auto")
        command.add_argument("--offline", action=argparse.BooleanOptionalAction, default=None)
        command.add_argument("--models-dir", type=Path, default=None)
        command.add_argument("--recordings-dir", type=Path, default=None)
        command.add_argument("--transcripts-dir", type=Path, default=None)
    return root


def settings_for(args: argparse.Namespace) -> Settings:
    path = args.config
    if path is None and Path("classscribe.toml").is_file():
        path = Path("classscribe.toml")
    return load_settings(path, vars(args))


def list_devices() -> None:
    devices = RecordingService(backend_factory=WasapiBackend).devices()
    for source, heading in (
        ("system", "SYSTEM OUTPUT / LOOPBACK DEVICES"),
        ("microphone", "MICROPHONES"),
    ):
        print(heading)
        for device in devices:
            if device.source == source:
                default = " (default)" if device.is_default else ""
                print(
                    f"[{device.id}] {device.name}{default} | "
                    f"{device.sample_rate} Hz, {device.channels} ch"
                )


def run_record(args: argparse.Namespace, settings: Settings) -> None:
    def prepared(directory: Path, session: Session, devices: list[Device]) -> None:
        print(f"ClassScribe\n\nCourse: {session.course}\nTitle: {session.title}")
        print(f"System audio: {devices[0].name}")
        print(f"Microphone: {devices[1].name if len(devices) > 1 else 'disabled'}")
        print(f"Session: {session.session_id}\nDirectory: {directory}", flush=True)

    announced = False

    def progress(elapsed: float) -> None:
        nonlocal announced
        if not announced:
            print("Recording started. Press Ctrl+C to stop.", flush=True)
            announced = True
        if sys.stdout.isatty():
            print(f"\rRecording: {timestamp(elapsed)}", end="", flush=True)

    service = RecordingService(backend_factory=WasapiBackend, recorder=record_session)
    result = service.record(
        settings,
        args.title,
        args.course,
        output_device=args.output_device,
        microphone_device=args.microphone_device,
        microphone=args.microphone,
        prepared=prepared,
        progress=progress,
        duration=args.duration,
    )
    print(f"\nRecording saved: {result.directory}")
    if args.transcribe:
        output = transcribe(settings, result.directory, result.session)
        print(f"Transcript: {output}")


def run_youtube(args: argparse.Namespace, settings: Settings) -> None:
    service = YouTubeService(client_factory=YtDlpClient, importer=import_youtube_session)
    if args.inspect:
        info = service.inspect_dict(settings, args.url)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return

    def prepared(directory: Path, session: Session, metadata: YouTubeMetadata) -> None:
        print(f"ClassScribe YouTube Import\n\nCourse: {session.course}\nTitle: {session.title}")
        print(f"Source: {metadata.url}")
        if metadata.channel:
            print(f"Channel: {metadata.channel}")
        print(f"Session: {session.session_id}\nDirectory: {directory}", flush=True)

    result = service.import_session(
        settings,
        args.url,
        args.title,
        args.course,
        prepared=prepared,
    )
    print(f"YouTube audio saved: {result.directory}")
    if args.transcribe:
        output = transcribe(settings, result.directory, result.session)
        print(f"Transcript: {output}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    try:
        settings = settings_for(args)
        if args.command == "devices":
            list_devices()
        elif args.command == "record":
            run_record(args, settings)
        elif args.command == "youtube":
            run_youtube(args, settings)
        elif args.command == "transcribe":
            manager = SessionManager(settings.recordings_dir)
            directory, session = manager.find(args.session_id)
            result = transcribe(settings, directory, session)
            print(f"Transcript: {result}")
        elif args.command == "doctor":
            from classscribe.doctor import diagnose

            report, ok = diagnose(settings, inference=args.device is not None)
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                for key, value in report.items():
                    print(f"{key}: {value}")
                if args.device is None:
                    print("Actual inference test: classscribe doctor --device cuda --model tiny")
            return 0 if ok else 1
        return 0
    except KeyboardInterrupt:
        print("\nCancelled. Original audio and partial work are preserved.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())
