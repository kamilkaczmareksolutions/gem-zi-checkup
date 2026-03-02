"""Checkpoint store — tracks which threads have been analysed and their fingerprints."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .schemas import Thread

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "results" / "youtube_insights" / "state"


def _thread_fingerprint(thread: Thread) -> str:
    """Deterministic hash over the full conversation content.

    Any new reply, edit, or deletion changes the fingerprint → triggers reanalysis.
    """
    parts: list[str] = []
    for c in thread.all_comments:
        parts.append(f"{c.comment_id}|{c.text}|{c.updated_at}")
    raw = "\n".join(sorted(parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class CheckpointStore:
    def __init__(self, path: Path | None = None):
        self._path = path or (STATE_DIR / "checkpoint.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    # ── persistence ─────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "last_run_at": None,
            "playlist_id": None,
            "known_video_ids": [],
            "threads": {},
        }

    def save(self):
        self._data["last_run_at"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        logger.info("Checkpoint saved → %s", self._path)

    # ── queries ─────────────────────────────────────────────────────

    @property
    def known_video_ids(self) -> list[str]:
        return self._data.get("known_video_ids", [])

    def set_playlist(self, playlist_id: str, video_ids: list[str]):
        self._data["playlist_id"] = playlist_id
        self._data["known_video_ids"] = video_ids

    def diff_threads(self, threads: list[Thread]) -> tuple[list[Thread], list[Thread]]:
        """Partition threads into (new_or_changed, unchanged).

        Returns only threads whose fingerprint differs from checkpoint
        or that are entirely new.
        """
        stored = self._data.get("threads", {})
        new_or_changed: list[Thread] = []
        unchanged: list[Thread] = []

        for t in threads:
            fp = _thread_fingerprint(t)
            prev = stored.get(t.thread_id)
            if prev is None or prev.get("fingerprint") != fp:
                new_or_changed.append(t)
            else:
                unchanged.append(t)

        return new_or_changed, unchanged

    def update_threads(self, threads: list[Thread]):
        """Write current fingerprints for the given threads."""
        stored = self._data.setdefault("threads", {})
        for t in threads:
            stored[t.thread_id] = {
                "fingerprint": _thread_fingerprint(t),
                "video_id": t.video_id,
                "reply_count": t.reply_count,
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }

    # ── previous insights (for merging with new ones) ───────────────

    def get_previous_insights_path(self) -> Path | None:
        p = self._data.get("last_insights_path")
        if p and Path(p).exists():
            return Path(p)
        return None

    def set_insights_path(self, path: Path):
        self._data["last_insights_path"] = str(path)

    def get_previous_raw_insights_path(self) -> Path | None:
        p = self._data.get("last_raw_insights_path")
        if p and Path(p).exists():
            return Path(p)
        return None

    def set_raw_insights_path(self, path: Path):
        self._data["last_raw_insights_path"] = str(path)
