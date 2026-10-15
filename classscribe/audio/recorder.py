"""Recording lifecycle. This module never imports an inference backend."""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from classscribe.audio.devices import Device
from classscribe.audio.interfaces import AudioBackend, CaptureStream
from classscribe.audio.writer import TrackWriter
from classscribe.sessions.manager import SessionManager, now_iso
from classscribe.sessions.models import Session, Status
from classscribe.storage import exclusive_lock

logger = logging.getLogger(__name__)


class RecordingError(RuntimeError):
    pass


def record_session(
    manager: SessionManager,
    directory: Path,
    session: Session,
    backend: AudioBackend,
    devices: list[Device],
    *,
    progress: Callable[[float], None] = lambda _: None,
    wait: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
    duration: float | None = None,
) -> Session:
    if session.status != Status.CREATED:
        raise ValueError("Only a new session can be recorded")
    if [d.source for d in devices].count("system") != 1:
        raise ValueError("Select exactly one system playback device")
    if len({d.source for d in devices}) != len(devices):
        raise ValueError("Only one device per source is supported")
    origin = clock()
    writers: list[TrackWriter] = []
    streams: list[CaptureStream] = []
    error: BaseException | None = None
    started = False
    with exclusive_lock(directory):
        try:
            session.started_at = now_iso()
            session.system_audio_device = next(d.to_dict() for d in devices if d.source == "system")
            mic = next((d for d in devices if d.source == "microphone"), None)
            session.microphone_device = mic.to_dict() if mic else None
            session.microphone_audio_file = "microphone.wav" if mic else None
            session.transition(Status.RECORDING)
            manager.save(directory, session)
            for device in devices:
                writer = TrackWriter(directory, device, origin)
                writers.append(writer)
                streams.append(backend.open(device, writer.receive))
            # Open all streams before starting any. First-buffer ADC timestamps, not
            # the order of these calls, establish each track's timeline offset.
            for stream in streams:
                stream.start()
            started = True
            checkpoint = -1.0
            while True:
                elapsed = max(0.0, clock() - origin)
                for writer in writers:
                    if writer.error:
                        raise writer.error
                if any(not stream.active() for stream in streams):
                    raise RecordingError("Audio stream stopped unexpectedly (device disconnected?)")
                if elapsed - checkpoint >= 1:
                    session.tracks = {w.device.source: w.metadata() for w in writers}
                    session.duration_seconds = elapsed
                    manager.save(directory, session)
                    progress(elapsed)
                    checkpoint = elapsed
                if duration is not None and elapsed >= duration:
                    break
                wait(0.2)
        except KeyboardInterrupt as exc:
            if not started:
                error = exc
        except Exception as exc:
            error = exc
        finally:
            # Stop producers before draining queues and finalizing every WAV header.
            for stream in streams:
                try:
                    stream.close()
                except Exception as exc:
                    error = error or exc
            for writer in writers:
                writer.finish()
                error = error or writer.error
            session.tracks = {w.device.source: w.metadata() for w in writers}
            session.ended_at = now_iso()
            session.duration_seconds = max(0.0, clock() - origin)
            session.recording_finalized = started and error is None
            session.error = f"{type(error).__name__}: {error}" if error else None
            session.transition(Status.FAILED if error else Status.RECORDED)
            manager.save(directory, session)
    if error:
        logger.error("Recording failed; available PCM preserved in session %s", session.session_id)
        raise RecordingError(
            f"Recording failed: {session.error}. Audio preserved in {directory}"
        ) from error
    return session
