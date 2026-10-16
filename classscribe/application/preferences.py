"""Desktop preferences persisted without importing Qt or altering CLI TOML."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from classscribe.config import Settings, load_settings
from classscribe.storage import atomic_json


def defaults(base: Path) -> dict[str, Any]:
    settings = Settings(
        recordings_dir=base / "recordings",
        transcripts_dir=base / "transcripts",
        models_dir=base / "models",
    )
    return {
        **{k: str(v) if isinstance(v, Path) else v for k, v in asdict(settings).items()},
        "theme": "dark",
        "output_device": "",
        "microphone_device": "",
        "auto_transcribe": False,
    }


def validated(values: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings(None, values)
    if values.get("theme", "dark") not in {"dark", "light", "system"}:
        raise ValueError("Theme must be dark, light, or system")
    if type(values.get("auto_transcribe", False)) is not bool:
        raise ValueError("Automatic transcription must be a boolean")
    for key in ("output_device", "microphone_device"):
        if not isinstance(values.get(key, ""), str):
            raise ValueError("Device selection must be a name")
    for key in ("recordings_dir", "transcripts_dir", "models_dir"):
        if not str(values.get(key, "")).strip():
            raise ValueError("Storage directories must not be empty")
    return {
        **values,
        **{k: str(v.resolve()) if isinstance(v, Path) else v for k, v in asdict(settings).items()},
    }


class PreferenceStore:
    def __init__(self, path: Path, data_root: Path) -> None:
        self.path = path
        self.data_root = data_root

    def load(self) -> dict[str, Any]:
        values = defaults(self.data_root)
        if self.path.exists():
            values.update(json.loads(self.path.read_text(encoding="utf-8")))
        return validated(values)

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        result = validated(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, result)
        return result
