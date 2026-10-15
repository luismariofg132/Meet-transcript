"""Durable atomic metadata writes and exclusive operation locks."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


def atomic_json(path: Path, value: Any) -> None:
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def exclusive_lock(directory: Path) -> Iterator[None]:
    path = directory / ".operation.lock"
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RuntimeError(
            "Session is busy. If its process crashed, inspect the session and remove "
            ".operation.lock only after confirming no operation is running."
        ) from exc
    try:
        with handle:
            handle.write("ClassScribe operation in progress\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}"
