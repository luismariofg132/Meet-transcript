"""Unique runs, durable partial segments and transactional final publication."""

import json
import logging
import os
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager, now_iso
from classscribe.sessions.models import Session, Status
from classscribe.storage import atomic_json, exclusive_lock
from classscribe.transcription.chunks import audio_chunks, chunking_metadata
from classscribe.transcription.engine import Engine, load_engine
from classscribe.transcription.progress import TranscriptionProgress
from classscribe.transcription.timestamps import audio_interval
from classscribe.transcription.transcript import Segment, markdown, merge_segments

logger = logging.getLogger(__name__)


def resolve_audio(directory: Path, filename: str) -> Path:
    path = (directory / filename).resolve()
    if path.parent != directory.resolve() or path.suffix.lower() != ".wav":
        raise ValueError("Session audio must be a WAV file inside its session directory")
    return path


def transcribe_session(
    manager: SessionManager,
    directory: Path,
    session: Session,
    settings: Settings,
    *,
    engine_factory: Callable[[Settings], Engine] = load_engine,
    progress: Callable[[TranscriptionProgress], None] | None = None,
) -> Path:
    with exclusive_lock(directory):
        # Re-read under lock so an old in-memory status cannot start concurrent work.
        session = manager.load(directory)
        if (
            not session.recording_finalized
            or not session.tracks
            or session.status
            not in {
                Status.RECORDED,
                Status.COMPLETED,
                Status.FAILED,
            }
        ):
            raise ValueError("Transcription requires a successfully finalized recording")
        run_id = f"{settings.model}-{uuid4().hex}"
        run = settings.transcripts_dir / session.session_id / run_id
        run.mkdir(parents=True, exist_ok=False)
        report: dict[str, Any] = {
            "schema_version": 1,
            "session_id": session.session_id,
            "run_id": run_id,
            "status": "transcribing",
            "started_at": now_iso(),
            "model": settings.model,
            "requested_device": settings.device,
            "language": settings.language,
            "segments_preserved": 0,
            "stage": "loading_model",
            "chunking": chunking_metadata(),
            "timestamp_adjustments": {"clipped_ends": 0, "padding_segments_dropped": 0},
        }
        session.transition(Status.TRANSCRIBING)
        session.error = None
        session.transcription_runs.append(run_id)
        total_seconds = sum(t["frames"] / t["sample_rate"] for t in session.tracks.values())
        processed_seconds = 0.0

        def notify(stage: str, source: str = "", filename: str = "") -> None:
            if progress is not None:
                progress(
                    TranscriptionProgress(
                        stage,
                        processed_seconds,
                        total_seconds,
                        source,
                        filename,
                        report.get("device", ""),
                    )
                )

        try:
            manager.save(directory, session)
            atomic_json(run / "run.json", report)
            notify("loading_model")
            engine = engine_factory(settings)
            report.update(device=engine.device, compute_type=engine.compute_type)
            atomic_json(run / "run.json", report)
            segments: list[Segment] = []
            with (run / "segments.partial.jsonl").open("x", encoding="utf-8") as partial:
                for source, track in session.tracks.items():
                    segment_source = (
                        "media"
                        if session.source_kind == "youtube" and source == "system"
                        else source
                    )
                    offset = track["start_offset_seconds"]
                    if not track["frames"]:
                        continue
                    if offset is None:
                        raise ValueError("Nonempty track is missing its timeline offset")
                    for part in track["parts"]:
                        part_offset = part["start_frame"] / track["sample_rate"]
                        path = resolve_audio(directory, part["file"])
                        report.update(
                            stage="decoding_audio",
                            source=segment_source,
                            audio_file=part["file"],
                        )
                        notify("preparing_audio", segment_source, part["file"])
                        # Explicitly close the generator even on inference failure or
                        # cancellation, so temporary WAVs never wait for GC cleanup.
                        with closing(audio_chunks(path, run)) as windows:
                            for window in windows:
                                report.update(
                                    stage="inference",
                                    chunk_start_seconds=window.start,
                                    chunk_end_seconds=window.end,
                                    keep_start_seconds=window.keep_start,
                                    keep_end_seconds=window.keep_end,
                                )
                                atomic_json(run / "run.json", report)
                                notify("transcribing", segment_source, part["file"])
                                generated, language = engine.transcribe(
                                    window.path, settings.language
                                )
                                for raw in generated:
                                    if not raw.text.strip():
                                        continue
                                    try:
                                        interval = audio_interval(
                                            raw.start, raw.end, window.duration
                                        )
                                    except ValueError:
                                        # Numeric context only: never persist recognized text
                                        # in error diagnostics. repr also handles NaN/inf.
                                        report["invalid_timestamp"] = {
                                            "start": repr(raw.start),
                                            "end": repr(raw.end),
                                            "window_duration": window.duration,
                                        }
                                        raise
                                    if interval is None:
                                        report["timestamp_adjustments"][
                                            "padding_segments_dropped"
                                        ] += 1
                                        continue
                                    if interval[1] != raw.end:
                                        report["timestamp_adjustments"]["clipped_ends"] += 1
                                    audio_start = window.start + interval[0]
                                    audio_end = window.start + interval[1]
                                    segment = Segment(
                                        source=segment_source,
                                        start=offset + part_offset + audio_start,
                                        end=offset + part_offset + audio_end,
                                        text=raw.text.strip(),
                                        language=language,
                                        audio_file=part["file"],
                                        audio_start=audio_start,
                                        audio_end=audio_end,
                                    )
                                    # Compare on the original part timeline. Keep the
                                    # whole segment; do not split text or compare sources.
                                    if not window.owns(segment.audio_start, segment.audio_end):
                                        continue
                                    partial.write(
                                        json.dumps(segment.to_dict(), ensure_ascii=False) + "\n"
                                    )
                                    partial.flush()
                                    os.fsync(partial.fileno())
                                    segments.append(segment)
                                    report["segments_preserved"] = len(segments)
                                processed_seconds += window.keep_end - window.keep_start
                                notify("transcribing", segment_source, part["file"])
            notify("merging")
            transcript = {
                "schema_version": 1,
                "session_id": session.session_id,
                "run_id": run_id,
                "title": session.title,
                "course": session.course,
                "started_at": session.started_at,
                "duration_seconds": session.duration_seconds,
                "language": settings.language,
                "detected_languages": sorted({segment.language for segment in segments}),
                "model": settings.model,
                "device": engine.device,
                "compute_type": engine.compute_type,
                "timeline": "seconds from common recording origin",
                "chunking": report["chunking"],
                "segments": [segment.to_dict() for segment in merge_segments(segments)],
            }
            if session.source_kind == "youtube":
                transcript["source_kind"] = "youtube"
                transcript["source_url"] = session.source_url
                transcript["youtube"] = session.youtube
            # A directory rename publishes the two artifacts together. Before this
            # point only partial files exist; consumers use result/ as the commit marker.
            report["stage"] = "publishing_artifacts"
            notify("publishing")
            staging = run / ".result.partial"
            staging.mkdir()
            atomic_json(staging / "transcript.json", transcript)
            with (staging / "transcript.md").open("x", encoding="utf-8") as handle:
                handle.write(markdown(transcript))
                handle.flush()
                os.fsync(handle.fileno())
            staging.rename(run / "result")
        except BaseException as exc:
            report.update(status="failed", ended_at=now_iso(), error_type=type(exc).__name__)
            report["recovery"] = (
                "Original audio is unchanged. Review stage/source/chunk and the partial journal. "
                "For CUDA failures run doctor --device cuda; "
                "retry with small/tiny or explicit CPU. "
                "For storage failures check free disk space. A retry creates a new run."
            )
            # Do not copy third-party exception bodies into logs/reports: they could
            # contain transcript fragments. The CLI receives our actionable errors.
            try:
                atomic_json(run / "run.json", report)
            except OSError:
                logger.error("Could not persist failed run metadata; check free disk space")
            session.transition(Status.FAILED)
            session.error = f"Transcription failed ({type(exc).__name__}); see run {run_id}"
            try:
                manager.save(directory, session)
            except OSError:
                logger.error("Could not persist failed session status; partial files remain")
            logger.error("Transcription failed; partial segments preserved in %s", run)
            raise
        report.update(status="completed", stage="completed", ended_at=now_iso())
        atomic_json(run / "run.json", report)
        session.transition(Status.COMPLETED)
        manager.save(directory, session)
        notify("completed")
        return run / "result"
