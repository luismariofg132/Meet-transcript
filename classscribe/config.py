"""Small validated TOML configuration; CLI overrides are applied last."""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

MODELS = ("tiny", "base", "small", "medium", "large-v3")
DEVICES = ("auto", "cpu", "cuda")


@dataclass(frozen=True)
class Settings:
    device: str = "auto"
    model: str = "small"
    language: str = "es"
    microphone: bool = True
    recordings_dir: Path = Path("recordings")
    transcripts_dir: Path = Path("transcripts")
    models_dir: Path = Path("models")
    offline: bool = False


def load_settings(path: Path | None, overrides: dict[str, Any]) -> Settings:
    values: dict[str, Any] = {}
    if path is not None:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    allowed = {field.name for field in fields(Settings)}
    if unknown := values.keys() - allowed:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    values.update({k: v for k, v in overrides.items() if k in allowed and v is not None})
    for key in ("recordings_dir", "transcripts_dir", "models_dir"):
        if key in values:
            if not isinstance(values[key], (str, Path)):
                raise ValueError(f"{key} must be a path")
            values[key] = Path(values[key]).expanduser()
    settings = Settings(**values)
    if settings.device not in DEVICES or settings.model not in MODELS:
        raise ValueError(f"device must be {DEVICES}; model must be {MODELS}")
    if not isinstance(settings.language, str) or not settings.language.strip():
        raise ValueError("language must be a language code or auto")
    if type(settings.microphone) is not bool or type(settings.offline) is not bool:
        raise ValueError("microphone and offline must be TOML booleans")
    return settings
