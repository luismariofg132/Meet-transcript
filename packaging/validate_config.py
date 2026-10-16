"""Fail before compilation if the yt-dlp memory safeguards are missing."""

import configparser
import shlex
import sys
from pathlib import Path


def validate_config(path: Path) -> None:
    config = configparser.ConfigParser(interpolation=None)
    with path.open(encoding="utf-8") as source:
        config.read_file(source)
    options = shlex.split(config["nuitka"]["extra_args"])
    required = {
        "--include-package=yt_dlp",
        "--nofollow-import-to=yt_dlp.extractor.lazy_extractors",
        "--low-memory",
    }
    missing = required.difference(options)
    if missing:
        raise ValueError(f"Missing yt-dlp packaging safeguards: {sorted(missing)}")
    if config["nuitka"]["mode"].strip() != "standalone":
        raise ValueError("ClassScribe requires standalone mode")
    print("PASS: yt-dlp inclusion, lazy registry exclusion and low-memory mode configured")


if __name__ == "__main__":
    validate_config(
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("pysidedeploy.spec")
    )
