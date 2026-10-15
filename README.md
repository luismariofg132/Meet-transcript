# ClassScribe

ClassScribe records university classes locally and transcribes them **after recording stops**.
Windows WASAPI loopback captures what you hear from Google Meet, Teams, Zoom, a browser,
or another desktop application. An optional microphone is recorded as a separate track.
It has no dependency on the meeting platform or its APIs.

This is an independent Python 3.12 project. It does not extend the YouTube application.
The initial release is a CLI MVP: no GUI, cloud service, live transcription, remote speaker
diarization, or AI study features.

## Workflow and architecture

```text
Meeting / Windows playback ─> WASAPI loopback ─> bounded queue ─> system WAV parts
Selected microphone       ─> WASAPI input    ─> bounded queue ─> microphone WAV parts
                              common monotonic recording timeline
                                         |
                              stop, drain, finalize audio
                                         |
                              load faster-whisper model
                                         |
                              CPU / NVIDIA CUDA inference
                                         |
                              partial JSONL ─> final JSON + Markdown
```

Whisper and CTranslate2 are lazily imported. `record --transcribe` closes both streams,
drains both queues, finalizes all WAV files, persists `recorded`, and terminates the audio
backend before importing the transcription service. No model runs during capture.

| Component | Responsibility |
| --- | --- |
| `classscribe/audio/devices.py` | Device mapping, IDs, exact-name/default selection |
| `classscribe/audio/interfaces.py` | Mockable audio backend and stream contracts |
| `classscribe/audio/wasapi.py` | Isolated PyAudioWPatch adapter and timestamp conversion |
| `classscribe/audio/writer.py` | Bounded queues, PCM16 WAV writing, silence gaps, rotation |
| `classscribe/audio/recorder.py` | Start/stop lifecycle, Ctrl+C, cleanup, metadata checkpoints |
| `classscribe/sessions/` | Unique identities, safe directories, status transitions |
| `classscribe/transcription/` | Lazy engine, CUDA, audio windows, runs, structured outputs |
| `classscribe/config.py`, `storage.py` | Validated TOML, atomic JSON, operation locks |
| `classscribe/doctor.py`, `cli/` | Diagnostics and user commands |

The design was informed by inspection of the reference repository's
[runtime setup](https://github.com/luismariofg132/Youtube_Transcrip/blob/main/runtime.py)
and [transcription code](https://github.com/luismariofg132/Youtube_Transcrip/blob/main/transcribe.py).
The new implementation retains lazy model loading, process-local Windows DLL discovery,
explicit device selection, model caching, and partial recovery, without YouTube dependencies.

## Installation

Use 64-bit **Python 3.12** and Windows 10/11 for capture. In a checkout of this project:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[audio,transcription]"
.\.venv\Scripts\python.exe -m classscribe --help
```

If the Python launcher is unavailable, use a Python 3.12 executable or
`uv venv --python 3.12 .venv`, then `uv pip install -e ".[audio,transcription]"`.
Activate `.venv` to use `classscribe` directly, or keep using the explicit Python path.
No system FFmpeg executable is required; faster-whisper uses PyAV.

### CPU installation

The installation above supports CPU transcription. Select `--device cpu`. Linux can
transcribe session directories copied from Windows, but cannot capture audio in this MVP:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[transcription]'
.venv/bin/python -m classscribe doctor --device cpu --model tiny
```

`small` is the default model. Supported models: `tiny`, `base`, `small`, `medium`, `large-v3`.
Each model downloads from Hugging Face on its first use and is cached under `models/`.
Cached models are preferred without a network lookup. `--offline` prohibits downloads;
a missing cache produces an error. Model weights are never part of Git.

### NVIDIA CUDA installation

Install a suitable NVIDIA driver. The `nvidia-smi` CUDA version is driver capability,
not proof that inference runtime libraries are installed. Current upstream requirements
are [CUDA 12 cuBLAS and cuDNN 9](https://github.com/SYSTRAN/faster-whisper#gpu).

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[audio,transcription,cuda]"
.\.venv\Scripts\python.exe -m classscribe doctor --device cuda --model tiny
```

On Windows, the CUDA extra installs cuBLAS; CTranslate2 Windows wheels in the supported
4.x series may bundle cuDNN. If your installed wheel does not, install cuDNN 9 from
[NVIDIA](https://developer.nvidia.com/cudnn-downloads) and put its DLL directory on the
process PATH. The app discovers DLLs inside installed `ctranslate2` and `nvidia` packages,
retains `os.add_dll_directory` handles, and only adjusts its own process environment.
It does not change system settings. Missing Microsoft runtime DLLs can require the
[Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

On Linux, the CUDA extra also installs cuDNN. Set the library path before starting Python:

```bash
.venv/bin/python -m pip install -e '.[transcription,cuda]'
export LD_LIBRARY_PATH="$(.venv/bin/python -c 'import nvidia.cublas, nvidia.cudnn; print(str(nvidia.cublas.__path__[0]) + "/lib:" + str(nvidia.cudnn.__path__[0]) + "/lib")')${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.venv/bin/python -m classscribe doctor --device cuda --model tiny
```

CUDA prefers `int8_float16` when CTranslate2 reports support; other supported GPU compute
types are considered on the same GPU. CPU prefers `int8`. See
[CTranslate2 compute types](https://opennmt.net/CTranslate2/quantization.html).
Inference is unbatched with one model shared sequentially by both tracks. Start with `small`
or `tiny` on limited VRAM. `auto` chooses CUDA if CTranslate2 detects a GPU, otherwise CPU.
If the selected CUDA runtime fails, **the job fails; it never silently retries on CPU**.

## Commands

Examples assume an activated environment; `python -m classscribe` is interchangeable
with `classscribe`.

### Diagnostics and devices

```powershell
classscribe doctor
classscribe doctor --json
classscribe doctor --device cuda --model tiny
classscribe doctor --device cpu --model tiny --offline
classscribe devices
```

Plain `doctor` reports Python, OS, package status, default output/microphone, GPU name,
VRAM/driver information, and CTranslate2 import/device detection. It does not load a model.
Passing `--device` explicitly performs synthetic one-second inference with VAD disabled
and consumes the segment generator. Only this test may report CUDA inference as passed.
It can download the chosen model unless `--offline` is set. A diagnostic never records
the microphone. A nonzero exit code means a required check failed; hardware visibility
alone never proves inference works.

Device listing shows WASAPI **loopback** IDs for system audio and WASAPI input IDs for
microphones. Defaults are marked. IDs are PortAudio indices, not separate consecutive
lists starting at zero; they can change after reconnecting hardware. Selection accepts
an exact name (case-insensitive) or an ID; ambiguous/missing selections fail clearly.
[PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) exposes output loopbacks as input
devices. Stereo Mix, virtual cables, extensions, and meeting APIs are unnecessary.

### Recording

```powershell
classscribe record --title "Memoria Cache" --course "Arquitectura de Computadores"
classscribe record --title "Clase" --no-microphone
classscribe record --title "Clase" --output-device 10 --microphone-device 4
classscribe record --title "Prueba" --no-microphone --duration 15
```

Replace `10` and `4` with your actual IDs. Press **Ctrl+C once** to stop and finalize.
A single-line elapsed timer appears in an interactive terminal. Redirected output is
quiet during capture. Microphone capture is enabled by default; use `--no-microphone`
if none is available. `--microphone` overrides a disabled config default; supplying
`--microphone-device` also enables it unless contradictory `--no-microphone` is supplied.

### Transcription and combined workflow

```powershell
classscribe transcribe SESSION_ID --model small --device auto --language es
classscribe transcribe SESSION_ID --model medium --device cpu --offline
classscribe record --title "Clase" --course "Arquitectura" --transcribe --device cuda
```

Use the **full session ID** printed at recording startup, or the exact session directory
name. Lookup uses `recordings/`; override with `--recordings-dir`. Every transcription
creates a fresh run, including retries with the same model. Original audio and all earlier
outputs remain intact. `--language auto` detects language per audio window; detected
languages are recorded per segment and in the final result.

## Configuration

Copy `classscribe.example.toml` to `classscribe.toml`, which is ignored by Git:

```toml
device = "auto"
model = "small"
language = "es"
microphone = true
offline = false
recordings_dir = "recordings"
transcripts_dir = "transcripts"
models_dir = "models"
```

Precedence: built-in defaults, then TOML, then explicit CLI arguments. Relative paths
are relative to the current working directory, including those in TOML. Put `--config`
before the subcommand: `classscribe --config D:\Classes\classscribe.toml record --title "Clase"`.
Use a stable working directory or absolute configured directories to find old sessions.
Unknown keys and invalid settings fail instead of being ignored.

## Local files and schemas

```text
recordings/
  2026-10-15_183000_clase_<unique-suffix>/
    session.json
    system.wav
    system-0002.wav              # only when a WAV part exceeds 1 GiB
    microphone.wav              # optional, independently rotated
transcripts/
  <session-id>/
    small-<unique-run-id>/
      run.json
      segments.partial.jsonl    # durable segment journal, also retained on success
      result/                   # published together only after successful inference
        transcript.json
        transcript.md
models/                         # shared model cache
```

Session directory and ID are never reused; metadata evolves atomically. Session JSON
contains schema/application versions, title/course, UTC start/end times, duration,
platform, device descriptions, audio filenames, sample rates/channel counts and per-track
timing/part metadata. It omits hostnames, account names and machine serial numbers.
States are `created → recording → recorded → transcribing → completed`. Errors become
`failed`; completed or failed transcription runs can be re-transcribed when the original
recording was successfully finalized. An exclusive session lock prevents simultaneous
transcription operations.

Each final JSON segment has `source`, `start`, `end`, `text`, `language`, `audio_file`,
`audio_start` and `audio_end`. `start/end` use the common session timeline; `audio_start/end`
seek within the named WAV part. Segments from both tracks are sorted chronologically,
preserving overlaps. `CLASE` in Markdown denotes **all system playback**, and `YO` denotes
microphone audio. Neither is a claim about who was speaking. No remote speaker diarization
is performed.

### Track synchronization and reliability

Each PortAudio ADC timestamp is mapped to `perf_counter()` using the callback's current
PortAudio time; the streams are not assumed to share an epoch or start simultaneously.
The first captured buffer determines each track's `start_offset_seconds`. When ADC timing
is unavailable, callback arrival minus buffer duration is used and explicitly recorded
as `callback_minus_buffer`. Initial offsets are approximate: callback scheduling and driver
timing affect accuracy. Hardware clocks can drift; no sample-rate drift correction is
implemented. Timing discrepancies over 100 ms are not silently ignored: forward gaps
insert silence, backward discontinuities fail capture. Inspect timing metadata when
precise alignment is important.

Recording uses PCM16 at each device's native rate and up to two channels, a 128-buffer
queue per source (1024-frame callbacks), and one disk writer per track. Audio is never
accumulated for the entire class. Every write patches the WAV header; periodic flush/fsync
and atomic metadata checkpoints reduce recoverable loss. WAV rotates at 1 GiB to avoid
RIFF's 4 GiB limit. At 48 kHz stereo, system audio alone takes roughly 0.69 GB/hour.
Ensure adequate disk space and prevent sleep during class. Original audio is never deleted.

Disconnects, PortAudio error flags, queue overflows and disk failures stop capture and
finalize all possible files. A failed capture is not automatically transcribed; preserve
and inspect its audio first. Power loss, force-kill, disk exhaustion and faulty drivers
cannot guarantee complete recovery. Files may need manual WAV/header repair; crash recovery
is not automatic. A stale `.operation.lock` should only be removed after confirming no
ClassScribe process is using that session. Do not mark a damaged recording as finalized
without validating its files and timing metadata.

Transcription decodes at most a five-minute audio window at once. This bounds audio memory,
but words at window boundaries can lose context. The original recording remains continuous
within each WAV part. Text segments are held in memory for the final chronological merge;
the segment journal is flushed and fsynced after each segment. On failure, inspect
`segments.partial.jsonl` and `run.json`; rerunning starts a new run, not an automatic resume.
A final `result/` directory is the publication marker. If a crash happens after publication
but before status metadata updates, the published result is usable; session status may be stale.

## Privacy and responsibility

All recordings and inference stay local. No OpenAI API, API keys, analytics, telemetry,
automatic uploads, or cloud transcription are used. Hugging Face telemetry and implicit
authentication are disabled in the inference process. Internet is needed only for package
installation and uncached model downloads; `--offline` requires an existing model cache.
Audio files, transcripts, caches, logs and local config are excluded from Git.

You are responsible for ensuring you have permission to record and transcribe the class
or meeting. System loopback captures **all playback on the selected Windows endpoint**,
including notifications and other applications. The app does not isolate Meet audio.
Speaker playback may also enter the microphone acoustically; headphones can reduce this.
Files are ordinary local files, without application-level encryption or automatic retention.

## Troubleshooting and limitations

| Symptom | Action |
| --- | --- |
| Audio backend missing | Install the `audio` extra on Windows and run `devices` |
| No default microphone | Select an available input or use `--no-microphone` |
| Empty or wrong system audio | Select the loopback of the endpoint the meeting uses |
| Device ID stopped working | Re-run `devices`; reconnects can change IDs |
| Unsupported format / Bluetooth change | Use a stable endpoint; test a short recording first |
| Capture stops with overflow | Reduce other disk/CPU load, use local storage, inspect preserved audio |
| Missing CUDA DLL | Install CUDA 12 cuBLAS/cuDNN 9 and MSVC runtime; run the inference doctor |
| CUDA out of memory | Close GPU-heavy apps after class, select `small`/`tiny`, or explicitly choose CPU |
| Offline model missing | Download once without `--offline`, then rerun offline |
| Interrupted transcription | Keep partial JSONL; rerun the session to create a new result |
| Poor recognition | Check source recording quality, language, and try a larger model |

Windows-first capture, all-playback loopback, approximate timing, independent clock drift,
overlapping speech, and recognition errors are MVP limitations. A long silent interval can
depend on endpoint/driver callback behavior. There is no hot device switching, pause/resume,
sample-accurate synchronization, echo cancellation, SRT/VTT export, live transcription,
speaker diarization, automatic meeting joining, or study-generation pipeline.

## Development and validation

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Tests use temporary directories, synthetic PCM and fake hardware/inference interfaces.
Network sockets are disabled in the test process. They require no devices, GPU, model
downloads, network, or meeting account. If your sandbox cannot write the default temporary
directory, use `python -m pytest --basetemp .tools/pytest-temp` (this directory is disposable).
The Windows/Linux GitHub Actions matrix runs tests, Ruff lint and format checks, installing
only the development extra. CI does **not** validate actual WASAPI capture or CUDA hardware.

Before relying on a full class, manually test a short recording on your endpoint, listen
to both tracks, verify offsets and a playback-silence-resume interval, then run an explicit
inference doctor. See `docs/VALIDATION.md` for the checks actually executed during implementation.

## Next phase

After validating long recordings and synchronization on target Windows hardware, build a
separate academic study-processing pipeline over the versioned transcript schema:
structured notes, summaries, concepts, examples, potential exam questions and flashcards.
Keep source timestamps and original audio references so generated material can be checked.
That pipeline is intentionally outside this MVP.
