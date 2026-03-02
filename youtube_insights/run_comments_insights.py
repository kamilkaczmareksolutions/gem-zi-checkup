#!/usr/bin/env python3
"""GEM YouTube Comments Insights — entrypoint.

Usage:
    python -m youtube_insights

Required env vars (in .env):
    YOUTUBE_API_KEY       — YouTube Data API v3 key
    GEMINI_API_KEY        — Google Gemini API key
    YOUTUBE_PLAYLIST_ID   — playlist to analyse

Optional env var:
    INSIGHTS_CONFIG  — path to config YAML (defaults to youtube_insights/config.example.yaml)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .checkpoint_store import CheckpointStore
from .gemini_analyzer import GeminiAnalyzer
from .report_builder import build_report, save_report
from .schemas import Insight, Thread, VideoMeta
from .youtube_client import YouTubeClient

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "results" / "youtube_insights" / "raw"

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("youtube_insights")


def load_config() -> dict:
    config_path = os.getenv("INSIGHTS_CONFIG",
                            str(Path(__file__).parent / "config.example.yaml"))
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_raw_snapshot(threads: list[Thread], timestamp: str):
    """Write all fetched threads as JSONL for auditability."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"threads_snapshot_{timestamp}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for t in threads:
            obj = {
                "thread_id": t.thread_id,
                "video_id": t.video_id,
                "top_comment": {
                    "id": t.top_comment.comment_id,
                    "author": t.top_comment.author,
                    "text": t.top_comment.text,
                    "published_at": t.top_comment.published_at,
                    "updated_at": t.top_comment.updated_at,
                    "like_count": t.top_comment.like_count,
                },
                "replies": [
                    {
                        "id": r.comment_id,
                        "author": r.author,
                        "text": r.text,
                        "published_at": r.published_at,
                        "updated_at": r.updated_at,
                        "like_count": r.like_count,
                    }
                    for r in t.replies
                ],
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    logger.info("Raw snapshot saved → %s (%d threads)", path, len(threads))


def _save_raw_insights(insights: list[Insight], path: Path):
    """Persist extracted insights so they survive aggregation failures."""
    data = [
        {
            "insight_type": i.insight_type,
            "topic": i.topic,
            "description": i.description,
            "severity": i.severity,
            "actionability": i.actionability,
            "buyer_intent": i.buyer_intent,
            "evidence_thread_ids": i.evidence_thread_ids,
            "source_video_ids": i.source_video_ids,
        }
        for i in insights
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Raw insights saved → %s (%d items)", path, len(data))


def _load_raw_insights(path: Path) -> list[Insight]:
    """Load previously saved raw insights."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        Insight(
            insight_type=d["insight_type"],
            topic=d["topic"],
            description=d["description"],
            severity=d["severity"],
            actionability=d["actionability"],
            buyer_intent=d["buyer_intent"],
            evidence_thread_ids=d.get("evidence_thread_ids", []),
            source_video_ids=d.get("source_video_ids", []),
        )
        for d in data
    ]


def _find_latest_raw_insights() -> Path | None:
    """Find the most recent raw_insights_*.json in RAW_DIR."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(RAW_DIR.glob("raw_insights_*.json"), reverse=True)
    return candidates[0] if candidates else None


def reaggregate():
    """Re-aggregate from previously saved raw insights (no YouTube/extraction)."""
    cfg = load_config()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        logger.error("GEMINI_API_KEY not set in .env")
        sys.exit(1)

    raw_path = _find_latest_raw_insights()
    if not raw_path:
        logger.error("No raw_insights_*.json found in %s — run full pipeline first.", RAW_DIR)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("GEM YouTube Insights — re-aggregation from %s", raw_path.name)
    logger.info("=" * 60)

    raw_insights = _load_raw_insights(raw_path)
    logger.info("Loaded %d raw insights", len(raw_insights))

    gemini_cfg = cfg.get("gemini", {})
    analyzer = GeminiAnalyzer(
        api_key=gemini_key,
        model=gemini_cfg.get("model", "gemini-2.5-flash-lite"),
        temperature=gemini_cfg.get("temperature", 0.2),
        batch_token_budget=gemini_cfg.get("batch_token_budget", 10_000),
        max_output_tokens=gemini_cfg.get("max_output_tokens", 4096),
    )

    aggregated = analyzer.aggregate_insights(raw_insights)
    logger.info("Aggregated topics: %d", len(aggregated))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    insights_path = RAW_DIR / f"aggregated_insights_{ts}.json"
    with open(insights_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2)

    report_md = build_report(
        aggregated, videos=[], total_threads=0, analysed_threads=0, skipped_threads=0,
    )
    report_path = save_report(report_md, ts)

    logger.info("=" * 60)
    logger.info("Re-aggregation complete. Report: %s", report_path)
    logger.info("=" * 60)


def _parse_max_batches() -> int | None:
    for i, arg in enumerate(sys.argv):
        if arg == "--max-batches" and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return None


def main():
    if "--reaggregate" in sys.argv:
        reaggregate()
        return

    max_batches = _parse_max_batches()
    cfg = load_config()

    playlist_id = os.getenv("YOUTUBE_PLAYLIST_ID", "").strip()
    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not playlist_id:
        logger.error("YOUTUBE_PLAYLIST_ID not set in .env")
        sys.exit(1)
    if not youtube_key:
        logger.error("YOUTUBE_API_KEY not set in .env")
        sys.exit(1)
    if not gemini_key:
        logger.error("GEMINI_API_KEY not set in .env")
        sys.exit(1)

    yt = YouTubeClient(api_key=youtube_key,
                       max_results=cfg.get("youtube", {}).get("max_results_per_page", 100))
    gemini_cfg = cfg.get("gemini", {})
    analyzer = GeminiAnalyzer(
        api_key=gemini_key,
        model=gemini_cfg.get("model", "gemini-2.5-flash-lite"),
        temperature=gemini_cfg.get("temperature", 0.2),
        batch_token_budget=gemini_cfg.get("batch_token_budget", 10_000),
        max_output_tokens=gemini_cfg.get("max_output_tokens", 4096),
    )
    checkpoint = CheckpointStore()

    # ── 1. Discover videos ──────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("GEM YouTube Insights — pipeline start")
    logger.info("=" * 60)

    videos = yt.list_playlist_videos(playlist_id)
    video_ids = [v.video_id for v in videos]
    video_titles = {v.video_id: v.title for v in videos}
    checkpoint.set_playlist(playlist_id, video_ids)

    # ── 2. Fetch all threads ────────────────────────────────────────
    all_threads: list[Thread] = []
    for v in videos:
        threads = yt.fetch_threads(v.video_id)
        v.comment_count = sum(1 + t.reply_count for t in threads)
        all_threads.extend(threads)

    logger.info("Total threads fetched: %d", len(all_threads))

    # ── 3. Diff against checkpoint ──────────────────────────────────
    new_or_changed, unchanged = checkpoint.diff_threads(all_threads)
    logger.info("New/changed: %d, unchanged: %d", len(new_or_changed), len(unchanged))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    # Always save raw snapshot of all threads for audit trail
    save_raw_snapshot(all_threads, ts)

    if not new_or_changed:
        logger.info("No new or changed threads — nothing to analyse.")
        # Still generate report from previously saved insights
        prev_path = checkpoint.get_previous_insights_path()
        if prev_path:
            logger.info("Regenerating report from previous insights: %s", prev_path)
            with open(prev_path, "r", encoding="utf-8") as f:
                prev_insights_data = json.load(f)
            report_md = build_report(
                prev_insights_data,
                videos,
                total_threads=len(all_threads),
                analysed_threads=0,
                skipped_threads=len(unchanged),
            )
            save_report(report_md, ts)
        else:
            logger.info("No previous insights found. Run again when new comments appear.")
        checkpoint.save()
        return

    # ── 4. Extract insights (batched) ───────────────────────────────
    raw_insights = analyzer.extract_insights(new_or_changed, video_titles,
                                             max_batches=max_batches)
    logger.info("Raw insights extracted: %d", len(raw_insights))

    # Persist raw insights BEFORE aggregation so they survive crashes
    raw_insights_path = RAW_DIR / f"raw_insights_{ts}.json"
    _save_raw_insights(raw_insights, raw_insights_path)

    # Merge with previous raw insights for unchanged threads
    prev_raw_path = checkpoint.get_previous_raw_insights_path()
    if prev_raw_path and prev_raw_path.exists() and unchanged:
        prev_raw = _load_raw_insights(prev_raw_path)
        logger.info("Loaded %d previous raw insights for merge", len(prev_raw))
        raw_insights = raw_insights + prev_raw

    # ── 5. Aggregate and rank (batched Gemini — semantic dedup) ────
    aggregated = analyzer.aggregate_insights(raw_insights)
    logger.info("Aggregated topics: %d", len(aggregated))

    # Save aggregated + raw paths for future incremental runs
    insights_path = RAW_DIR / f"aggregated_insights_{ts}.json"
    with open(insights_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2)
    checkpoint.set_insights_path(insights_path)
    checkpoint.set_raw_insights_path(raw_insights_path)

    # ── 6. Build report ─────────────────────────────────────────────
    report_md = build_report(
        aggregated,
        videos,
        total_threads=len(all_threads),
        analysed_threads=len(new_or_changed),
        skipped_threads=len(unchanged),
    )
    report_path = save_report(report_md, ts)

    # ── 7. Update checkpoint ────────────────────────────────────────
    checkpoint.update_threads(all_threads)
    checkpoint.save()

    logger.info("=" * 60)
    logger.info("Pipeline complete. Report: %s", report_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
