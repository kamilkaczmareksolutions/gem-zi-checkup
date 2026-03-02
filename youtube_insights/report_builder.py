"""Build the final ROI-ranked Markdown report."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .schemas import VideoMeta

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "results" / "youtube_insights" / "reports"


def build_report(
    aggregated: list[dict],
    videos: list[VideoMeta],
    total_threads: int,
    analysed_threads: int,
    skipped_threads: int,
) -> str:
    """Produce the Markdown report content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    video_list = "\n".join(
        f"| {v.video_id} | {v.title} | {v.comment_count} |" for v in videos
    )

    # Split into categories
    questions = [a for a in aggregated if a.get("insight_type") == "question"]
    doubts = [a for a in aggregated if a.get("insight_type") == "doubt"]
    problems = [a for a in aggregated if a.get("insight_type") == "problem"]
    suggestions = [a for a in aggregated if a.get("insight_type") == "suggestion"]
    praise = [a for a in aggregated if a.get("insight_type") == "praise"]

    md = f"""# GEM YouTube Insights — Raport ROI

**Data raportu:** {now}
**Filmów w playliście:** {len(videos)}
**Wątków łącznie:** {total_threads}
**Przeanalizowanych (nowe/zmienione):** {analysed_threads}
**Pominiętych (bez zmian):** {skipped_threads}

---

## Filmy w playliście

| Video ID | Tytuł | Komentarzy |
|----------|-------|------------|
{video_list}

---

## Top tematy wg ROI score (co zaadresować najpierw)

{_rank_table(aggregated)}

---

## Najczęstsze pytania

{_section(questions)}

---

## Najczęstsze wątpliwości

{_section(doubts)}

---

## Najczęstsze problemy

{_section(problems)}

---

## Sugestie od widzów

{_section(suggestions)}

---

## Pochwały (co już działa dobrze)

{_section(praise)}

---

## Rekomendowane priorytety contentowe

{_priorities(aggregated)}

---

*Raport wygenerowany automatycznie przez `youtube_insights` (Gemini + YouTube Data API).*
"""
    return md


def _rank_table(items: list[dict]) -> str:
    if not items:
        return "_Brak danych._"
    rows = []
    for i, a in enumerate(items, 1):
        rows.append(
            f"| {i} | {a.get('topic','-')} | {a.get('insight_type','-')} | "
            f"{a.get('frequency',0)} | {a.get('roi_score',0):.2f} | "
            f"{a.get('avg_severity',0):.1f} | {a.get('avg_actionability',0):.1f} | "
            f"{a.get('avg_buyer_intent',0):.1f} |"
        )
    header = "| # | Temat | Typ | Częstość | ROI | Severity | Action. | Intent |\n"
    header += "|---|-------|-----|----------|-----|----------|---------|--------|"
    return header + "\n" + "\n".join(rows)


def _section(items: list[dict]) -> str:
    if not items:
        return "_Brak danych w tej kategorii._"
    parts = []
    for a in items:
        quotes = a.get("representative_quotes", [])
        quote_block = ""
        if quotes:
            quote_block = "\n".join(f"  > _{q}_" for q in quotes[:2])
        parts.append(
            f"### {a.get('topic', '-')} (ROI: {a.get('roi_score', 0):.2f})\n\n"
            f"{a.get('description', '-')}\n\n"
            f"- Częstość: {a.get('frequency', 0)}\n"
            f"- Severity: {a.get('avg_severity', 0):.1f} / Actionability: {a.get('avg_actionability', 0):.1f} / "
            f"Buyer Intent: {a.get('avg_buyer_intent', 0):.1f}\n"
            + (f"\n{quote_block}\n" if quote_block else "")
        )
    return "\n".join(parts)


def _priorities(aggregated: list[dict]) -> str:
    if not aggregated:
        return "_Brak danych._"
    # Top 5 actionable non-praise items
    actionable = [a for a in aggregated if a.get("insight_type") != "praise"][:5]
    if not actionable:
        return "_Brak priorytetowych tematów._"
    lines = []
    for i, a in enumerate(actionable, 1):
        lines.append(
            f"{i}. **{a.get('topic', '-')}** — {a.get('description', '-')} "
            f"(ROI: {a.get('roi_score', 0):.2f}, częstość: {a.get('frequency', 0)})"
        )
    return "\n".join(lines)


def save_report(content: str, timestamp: str | None = None) -> Path:
    """Write report to disk and return the file path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = REPORTS_DIR / f"roi_report_{ts}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Report saved → %s", path)
    return path
