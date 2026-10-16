"""Offline regression checks for the Windows compiler memory safeguards."""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
validate_config = runpy.run_path(str(ROOT / "packaging" / "validate_config.py"))["validate_config"]


def test_current_packaging_config():
    validate_config(ROOT / "packaging" / "pysidedeploy.spec")


@pytest.mark.parametrize(
    "removed",
    [
        "--nofollow-import-to=yt_dlp.extractor.lazy_extractors",
        "--low-memory",
        "--include-package=yt_dlp",
    ],
)
def test_packaging_guard_rejects_missing_safeguard(tmp_path, removed):
    source = (ROOT / "packaging" / "pysidedeploy.spec").read_text(encoding="utf-8")
    spec = tmp_path / "broken.spec"
    spec.write_text(source.replace(removed, ""), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing yt-dlp packaging safeguards"):
        validate_config(spec)
