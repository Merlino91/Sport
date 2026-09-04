import asyncio
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.youtube")

class YouTubeService:
    """
    Searches YouTube for official match highlights and generates
    native Stremio stream items using the 'ytId' property.
    """

    def __init__(self):
        self._search_url = "https://www.youtube.com/results?search_query={query}"
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def clean_search_query(self, title: str) -> str:
        """Cleans match title to optimize YouTube highlight search results."""
        cleaned = re.sub(r'\[.*?\]', '', title).strip()
        for sep in [" vs ", " vs. ", " - ", " v "]:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                t1 = parts[0].strip()
                t2 = parts[1].strip()
                return f"{t1} {t2} highlights"
        return f"{cleaned} highlights"

    async def search_highlight_video(self, match_title: str) -> Optional[Dict[str, str]]:
        """
        Searches YouTube for match highlights and returns the best video ID and title.
        """
        query = self.clean_search_query(match_title)
        url = self._search_url.format(query=urllib.parse.quote_plus(query))

        try:
            # Use doh_client to ensure reliable DNS resolution
            data, _ = await doh_client.get_raw(url, timeout=6.0)
            if not data:
                return None

            html = data.decode("utf-8", errors="ignore")

            # Extract video IDs
            video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if not video_ids:
                return None

            # Deduplicate preserving order
            unique_ids = []
            for vid in video_ids:
                if vid not in unique_ids:
                    unique_ids.append(vid)

            best_id = unique_ids[0]

            # Try to extract the title for this video ID
            title = f"{match_title} Highlights"
            title_pattern = re.compile(
                r'"videoId":"' + re.escape(best_id) + r'".*?"title":{"runs":\[{"text":"(.*?)"}\]',
                re.DOTALL
            )
            title_match = title_pattern.search(html)
            if title_match:
                title = title_match.group(1).replace("\\u0026", "&")

            return {"video_id": best_id, "title": title}
        except Exception as e:
            logger.warning("YouTube highlight search failed for '%s': %s", match_title, e)

        return None

    async def get_highlight_streams(self, match_title: str) -> List[Dict[str, Any]]:
        """
        Returns a Stremio stream item configured with the native 'ytId' parameter.
        This triggers Stremio's built-in player on Android TV, PC, FireStick, etc.
        """
        video = await self.search_highlight_video(match_title)
        if not video or not video.get("video_id"):
            return []

        vid_id = video["video_id"]
        title = video.get("title", f"{match_title} Highlights")

        return [
            {
                "name": "🎬 Sintesi Ufficiale (YouTube)",
                "title": f"{title} (1080p)",
                "ytId": vid_id,
            }
        ]

youtube_service = YouTubeService()