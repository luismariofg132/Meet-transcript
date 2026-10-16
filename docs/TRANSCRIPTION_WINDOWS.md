# Overlapping transcription windows

ClassScribe uses the existing faster-whisper engine and post-recording pipeline. It does
not make a second inference pass or compare embeddings. Internal defaults in
`classscribe/transcription/chunks.py` are:

```python
TRANSCRIPTION_WINDOW_SECONDS = 300
TRANSCRIPTION_OVERLAP_SECONDS = 15
```

No CLI flags, configuration keys, runtime dependencies, recording/session changes, or
new engines are introduced. `audio_chunks` accepts an explicit `seconds` and
`overlap_seconds` internally; values must be finite, the window positive, and
`0 <= overlap < window`. Rounded sample counts must also retain a positive stride.

## Window layout and ownership

Window starts advance by `window - overlap`: 0, 285, 570, 855 seconds. Start positions
are calculated in integer audio frames, avoiding cumulative floating-point drift.
Each `AudioWindow` exposes its temporary path, original-part `start` and `end`,
`keep_start`, `keep_end`, `is_last`, and calculated `duration`. All these bounds use
seconds into the original WAV part; temporary-file timestamps begin at zero.

For a 1,000-second WAV part:

| Inference window | Ownership interval |
| --- | --- |
| 0–300 | [0, 292.5) |
| 285–585 | [292.5, 577.5) |
| 570–870 | [577.5, 862.5) |
| 855–1,000 | [862.5, 1,000] |

Each neighboring pair divides its overlap at the overlap midpoint. Ownership intervals
are inclusive on the left and exclusive on the right; the final audio endpoint is
included. The rest of each window is context, not independently publishable content.

For every nonempty Whisper segment, the service validates its chunk-relative interval,
then computes:

```text
audio_start = window.start + raw.start
audio_end   = window.start + raw.end
start       = track.start_offset_seconds + part.start_frame / sample_rate + audio_start
end         = track.start_offset_seconds + part.start_frame / sample_rate + audio_end
midpoint    = (audio_start + audio_end) / 2
```

The complete segment is accepted only if `midpoint` belongs to that window's ownership
interval. Ownership uses original-part coordinates; session offsets are never compared
against part-relative ownership bounds. Text is never split, and valid timestamps are
not clipped to the ownership boundary.
A 291–295-second segment has midpoint 293 and belongs to the second window. A midpoint
exactly at 292.5 also belongs to the second window.

Before ownership is evaluated, model estimates are bounded to the **actual audio**
in the decoded window. Whisper/VAD can estimate a final endpoint beyond the WAV's
duration (for example, 296.50–301.86 in a 300-second window). When that tail extends
by at most 30 seconds (one Whisper decoding window), its end is clipped to the real
duration. Segments starting at or after the audio end contain no real audio and are
dropped. This also applies to the last window: real tail speech is retained with an
endpoint at EOF, not discarded because its estimated midpoint lies past EOF.

Negative, reversed, non-finite timestamps and overruns exceeding 30 seconds still
fail explicitly. This is a bounded tail policy, not arbitrary timestamp repair or
a guarantee of recognition accuracy. `run.json.timestamp_adjustments` records clipped
ends and padding-only drops, including estimates subsequently filtered by ownership.
On invalid estimates, `run.json.invalid_timestamp` includes the raw numeric coordinates
and window duration, without recognized text. Existing partial recovery is preserved.

Validation of the boundary fix: 210 offline tests passed, including 19 new boundary
cases covering recordings and YouTube imports, overlap ownership, EOF, padding-only
estimates and invalid-value recovery. Ruff lint/format and diff whitespace checks passed.
A separate real CUDA/small validation processed an isolated copy of a 6060.083125-second
imported WAV through the complete service: 932 segments published as JSON/Markdown,
three clipped endpoint estimates, zero padding-only drops, 457.1 seconds elapsed.
The original session and failed run were not changed. This verifies completion and
bounded timestamps, not manual transcription accuracy.

There is no text-based or global duplicate removal. Identical utterances at different
times survive, including adjacent intentional repetitions. System and microphone
segments are filtered independently, then merged chronologically using existing session
timestamps. Similar text and simultaneous speech from different sources remain intact.

## Edges and rotated parts

- Empty audio produces no windows. Audio at most 300 seconds produces one window owning
  the entire file, including the final endpoint.
- The loop stops as soon as a window reaches EOF. Audio exactly 585 seconds produces
  windows starting at 0 and 285, without a redundant 570-second window.
- A 301-second recording produces 0–300 and 285–301. The final decode contains 15 seconds
  of context plus one second of new audio, rather than a one-second standalone decode.
  Every multi-window final decode is longer than the overlap. Windows never exceed 300
  seconds or move backwards to create a larger-than-configured overlap.
- Zero overlap gives ordinary sequential windows, with each window owning its entire
  range. A short trailing decode is then unavoidable without changing that behavior.
- Segments crossing ownership boundaries remain whole and are assigned by midpoint.
- Each rotated WAV part starts its own window sequence. No overlap is added across
  `system.wav` and `system-0002.wav`; the existing part and track offsets determine
  session timestamps, while `audio_start/end` still seek within the named original part.

## Recovery and cost

Only accepted segments enter the durable `segments.partial.jsonl` journal. Accepted
segments are flushed/fsynced immediately, so an interrupted journal uses the same
ownership decisions as a successful transcript. The service explicitly closes the
window iterator on success, failure and cancellation, removing temporary WAV files even
when exception tracebacks remain alive. Iterators used elsewhere should likewise be
exhausted or explicitly closed. The temporary path is reused: consume each yielded
window before advancing the iterator.

Original WAVs are read-only. Audio copying uses blocks of at most five seconds and each
decode remains bounded by the window size. Normal long-recording inference audio overhead
approaches `300 / 285 - 1`, approximately 5.3%; this is not a measured runtime guarantee.
There is no extra global transcription pass. Final publication remains transactional:
failure preserves the accepted journal, does not publish `result/`, and retry creates
a new run without modifying the previous one.

Both `run.json` and `transcript.json` have an additive `chunking` field:

```json
{
  "window_seconds": 300,
  "overlap_seconds": 15,
  "deduplication": "midpoint_ownership"
}
```

Schema version remains 1; existing segment fields keep their meanings. Run diagnostics
also record the active chunk start/end and ownership bounds in original-part seconds.

## Remaining limitations

Midpoint ownership removes repeated window observations deterministically when their
time ranges agree. Whisper can produce different segmentation, text or timestamps in
neighboring contexts. Those differences can move an utterance's midpoint across the
ownership boundary and still cause a repeated or omitted fragment. No word-level
alignment, semantic reconciliation, or perfect boundary decoding is claimed. Context
also does not extend across rotated WAV part boundaries. These limitations are preferable
to arbitrarily splitting text or deleting legitimate repeated sentences by text alone.
