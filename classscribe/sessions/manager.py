import json
import logging
import platform
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from classscribe.sessions.models import Session
from classscribe.storage import atomic_json

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:64].rstrip("-")
    if not slug or slug.upper() in {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
    }:
        slug = "class-" + slug
    return slug


class SessionManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, title: str, course: str = "") -> tuple[Path, Session]:
        if not title.strip():
            raise ValueError("Session title must not be empty")
        self.root.mkdir(parents=True, exist_ok=True)
        for _ in range(10):
            identity = uuid4().hex
            date = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
            directory = self.root / f"{date}_{safe_slug(title)}_{identity[:12]}"
            try:
                directory.mkdir()
            except FileExistsError:
                continue
            session = Session(identity, title.strip(), course, now_iso(), platform.system())
            self.save(directory, session)
            return directory, session
        raise FileExistsError("Could not allocate a unique session directory")

    def save(self, directory: Path, session: Session) -> None:
        atomic_json(directory / "session.json", session.to_dict())

    def load(self, directory: Path) -> Session:
        return Session.from_dict(
            json.loads((directory / "session.json").read_text(encoding="utf-8"))
        )

    def find(self, identity: str) -> tuple[Path, Session]:
        matches = []
        for path in self.root.glob("*/session.json"):
            try:
                session = self.load(path.parent)
            except (OSError, ValueError, TypeError, KeyError):
                logger.warning("Skipping unreadable session metadata in %s", path.parent.name)
                continue
            if identity in (session.session_id, path.parent.name):
                matches.append((path.parent, session))
        if len(matches) != 1:
            raise ValueError(f"Expected one session for {identity!r}; found {len(matches)}")
        return matches[0]
