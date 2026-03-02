"""Data models for the YouTube GEM Insights pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Comment:
    comment_id: str
    author: str
    text: str
    published_at: str
    updated_at: str
    like_count: int = 0
    is_channel_owner: bool = False


@dataclass
class Thread:
    thread_id: str
    video_id: str
    top_comment: Comment
    replies: list[Comment] = field(default_factory=list)

    @property
    def all_comments(self) -> list[Comment]:
        return [self.top_comment] + self.replies

    @property
    def total_text(self) -> str:
        parts = []
        for c in self.all_comments:
            role = "[AUTHOR]" if c.is_channel_owner else "[VIEWER]"
            parts.append(f"{role} {c.author}: {c.text}")
        return "\n".join(parts)

    @property
    def reply_count(self) -> int:
        return len(self.replies)


@dataclass
class Insight:
    insight_type: str          # "question" | "doubt" | "problem" | "suggestion" | "praise"
    topic: str                 # short topic label
    description: str           # 1-2 sentence summary
    severity: int              # 1-5
    actionability: int         # 1-5
    buyer_intent: int          # 1-5 (how close to buying/subscribing decision)
    evidence_thread_ids: list[str] = field(default_factory=list)
    source_video_ids: list[str] = field(default_factory=list)


@dataclass
class AggregatedTopic:
    topic: str
    insight_type: str
    description: str
    frequency: int
    avg_severity: float
    avg_actionability: float
    avg_buyer_intent: float
    roi_score: float = 0.0
    evidence_thread_ids: list[str] = field(default_factory=list)
    source_video_ids: list[str] = field(default_factory=list)
    representative_quotes: list[str] = field(default_factory=list)


@dataclass
class VideoMeta:
    video_id: str
    title: str
    published_at: str
    comment_count: int = 0
