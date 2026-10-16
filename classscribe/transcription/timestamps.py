"""Bound model estimates to the actual audio before applying window ownership."""

import math

# Whisper predicts timestamps within 30-second decoding windows. A tail estimate
# can extend into the padded end of a window (including after VAD remapping).
# Bound that accommodation; do not silently repair arbitrary/corrupt coordinates.
MAX_TAIL_OVERRUN_SECONDS = 30.0


def audio_interval(start: float, end: float, duration: float) -> tuple[float, float] | None:
    """Intersect a valid estimate with real audio; None means padding-only speech.

    Negative, reversed, non-finite and excessive estimates remain errors. Text is
    never split here. Callers record adjustments and apply ownership to the bounded
    interval, so a last-window tail is retained without publishing time beyond EOF.
    """
    if (
        not all(math.isfinite(value) for value in (start, end, duration))
        or duration <= 0
        or start < 0
        or end < start
        or end > duration + MAX_TAIL_OVERRUN_SECONDS
    ):
        raise ValueError("Whisper returned an invalid chunk timestamp")
    if start >= duration:
        return None
    return start, min(end, duration)
