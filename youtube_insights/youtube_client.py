"""YouTube Data API v3 client — playlist videos + comment threads with full replies."""

from __future__ import annotations

import logging
import time
from typing import Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .schemas import Comment, Thread, VideoMeta

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 100
MAX_RETRIES = 4
BACKOFF_BASE = 2  # seconds


class YouTubeClient:
    def __init__(self, api_key: str, max_results: int = DEFAULT_MAX_RESULTS):
        self._service = build("youtube", "v3", developerKey=api_key)
        self._max_results = min(max_results, 100)

    # ── playlist → video IDs ────────────────────────────────────────

    def list_playlist_videos(self, playlist_id: str) -> list[VideoMeta]:
        """Return all videos in a playlist (handles pagination)."""
        videos: list[VideoMeta] = []
        page_token = None

        while True:
            resp = self._call(
                self._service.playlistItems().list,
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            for item in resp.get("items", []):
                snip = item["snippet"]
                vid = snip["resourceId"]["videoId"]
                videos.append(VideoMeta(
                    video_id=vid,
                    title=snip.get("title", ""),
                    published_at=snip.get("publishedAt", ""),
                ))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        logger.info("Playlist %s: found %d videos", playlist_id, len(videos))
        return videos

    # ── video → comment threads ─────────────────────────────────────

    def fetch_threads(self, video_id: str) -> list[Thread]:
        """Fetch all top-level comment threads for a video, with inline replies."""
        threads: list[Thread] = []
        page_token = None

        while True:
            resp = self._call(
                self._service.commentThreads().list,
                part="snippet,replies",
                videoId=video_id,
                maxResults=self._max_results,
                pageToken=page_token,
                textFormat="plainText",
                order="time",
            )
            for item in resp.get("items", []):
                thread = self._parse_thread(item, video_id)
                threads.append(thread)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # hydrate threads that may have truncated replies
        for t in threads:
            total_reply_count = self._get_total_reply_count(t.thread_id, resp_items=resp.get("items", []))
            if total_reply_count is None:
                continue
            if len(t.replies) < total_reply_count:
                t.replies = self._fetch_all_replies(t.thread_id)

        logger.info("Video %s: fetched %d threads", video_id, len(threads))
        return threads

    # ── full replies for a thread ───────────────────────────────────

    def _fetch_all_replies(self, thread_id: str) -> list[Comment]:
        """Paginate through comments.list to get every reply in a thread."""
        replies: list[Comment] = []
        page_token = None

        while True:
            resp = self._call(
                self._service.comments().list,
                part="snippet",
                parentId=thread_id,
                maxResults=100,
                pageToken=page_token,
                textFormat="plainText",
            )
            for item in resp.get("items", []):
                replies.append(self._parse_comment(item["snippet"], item["id"]))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return replies

    # ── parsing helpers ─────────────────────────────────────────────

    @staticmethod
    def _parse_thread(item: dict, video_id: str) -> Thread:
        top_snip = item["snippet"]["topLevelComment"]["snippet"]
        top_id = item["snippet"]["topLevelComment"]["id"]
        top_comment = YouTubeClient._parse_comment(top_snip, top_id)

        replies: list[Comment] = []
        for r in item.get("replies", {}).get("comments", []):
            replies.append(YouTubeClient._parse_comment(r["snippet"], r["id"]))

        return Thread(
            thread_id=item["id"],
            video_id=video_id,
            top_comment=top_comment,
            replies=replies,
        )

    @staticmethod
    def _parse_comment(snippet: dict, comment_id: str) -> Comment:
        return Comment(
            comment_id=comment_id,
            author=snippet.get("authorDisplayName", ""),
            text=snippet.get("textDisplay", ""),
            published_at=snippet.get("publishedAt", ""),
            updated_at=snippet.get("updatedAt", snippet.get("publishedAt", "")),
            like_count=snippet.get("likeCount", 0),
            is_channel_owner=snippet.get("authorChannelId", {}).get("value", "") == snippet.get("channelId", ""),
        )

    def _get_total_reply_count(self, thread_id: str, resp_items: list[dict]) -> int | None:
        for item in resp_items:
            if item["id"] == thread_id:
                return item["snippet"].get("totalReplyCount", 0)
        return None

    # ── retry wrapper ───────────────────────────────────────────────

    @staticmethod
    def _call(method, **kwargs):
        """Call a YouTube API method with exponential backoff on transient errors."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                return method(**kwargs).execute()
            except HttpError as e:
                if e.resp.status in (429, 500, 503) and attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE ** (attempt + 1)
                    logger.warning("YouTube API %d, retry %d/%d in %ds",
                                   e.resp.status, attempt + 1, MAX_RETRIES, wait)
                    time.sleep(wait)
                    continue
                raise
