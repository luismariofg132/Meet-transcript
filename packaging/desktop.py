"""Stable standalone script for pyside6-deploy/Nuitka discovery."""

import os
import sys
from importlib.util import find_spec

from classscribe.gui.app import main


def check_youtube_runtime() -> None:
    """Resolve the real YouTube extractor offline inside the packaged executable."""
    from classscribe.youtube import YtDlpClient

    youtube_dl = YtDlpClient()._load_yt_dlp()
    with youtube_dl({"quiet": True, "no_warnings": True}) as downloader:
        extractor = downloader.get_info_extractor("Youtube")
        if not extractor.suitable("https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
            raise RuntimeError("Packaged YouTube extractor cannot resolve a video URL")
    if "yt_dlp.extractor.lazy_extractors" in sys.modules:
        raise RuntimeError("Packaged YouTube support loaded the excluded lazy registry")
    if "__compiled__" in globals() and find_spec("yt_dlp.extractor.lazy_extractors") is not None:
        raise RuntimeError("The excluded lazy registry is still available in the bundle")


if __name__ == "__main__":
    if os.environ.get("CLASSSCRIBE_SMOKE_TEST") == "1":
        check_youtube_runtime()
    raise SystemExit(main())
