import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.dailymotion")

class DailymotionService:
    """Extracts sports highlights and direct .m3u8 HLS master streams from Dailymotion."""

    def __init__(self):
        self._api_base = "https://api.dailymotion.com"
        self._metadata_base = "https://www.dailymotion.com/player/metadata/video"

    def clean_search_query(self, title: str) -> str:
        """Cleans match title into effective search terms for highlights."""
        cleaned = title
        # Normalize separators
        for sep in [" vs ", " vs. ", " - ", " v "]:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                t1 = parts[0].strip()
                t2 = parts[1].strip()
                return f"{t1} {t2} highlights"

        return f"{cleaned} highlights"

    async def search_videos(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches Dailymotion for candidate highlight videos."""
        encoded_q = urllib.parse.quote_plus(query)
        url = f"{self._api_base}/videos?search={encoded_q}&fields=id,title,duration,created_time&limit={limit}"
        try:
            data = await doh_client.get_json(url)
            if isinstance(data, dict) and "list" in data:
                return data["list"]
        except Exception as e:
            logger.warning("Dailymotion search failed for query '%s': %s", query, e)

        return []

    async def get_stream_m3u8(self, video_id: str) -> Optional[str]:
        """Fetches the direct master .m3u8 stream manifest from Dailymotion player metadata."""
        url = f"{self._metadata_base}/{video_id}"
        try:
            data = await doh_client.get_json(url)
            if isinstance(data, dict):
                qualities = data.get("qualities", {})
                auto_list = qualities.get("auto", [])
                for item in auto_list:
                    if item.get("type") == "application/x-mpegURL" and "url" in item:
                        return item["url"]
        except Exception as e:
            logger.warning("Failed extracting m3u8 for Dailymotion video %s: %s", video_id, e)

        return None

    async def get_highlight_streams(self, match_title: str) -> List[Dict[str, Any]]:
        """
        Searches for highlight videos matching the match title and returns
        Stremio-compatible stream dictionaries with direct .m3u8 playback URLs.
        """
        search_query = self.clean_search_query(match_title)
        videos = await self.search_videos(search_query, limit=4)
        if not videos:
            return []

        # Filter videos by duration: between 100s (~1.5m) and 1200s (20m)
        candidates = [v for v in videos if 100 <= v.get("duration", 0) <= 1200]
        if not candidates:
            candidates = videos[:2]

        streams = []
        for vid in candidates[:2]:
            vid_id = vid.get("id")
            title = vid.get("title", "Highlights")
            duration_mins = vid.get("duration", 0) // 60
            dur_str = f" ({duration_mins} min)" if duration_mins else ""

            m3u8_url = await self.get_stream_m3u8(vid_id)
            if m3u8_url:
                streams.append({
                    "name": "🎬 Sintesi & Gol (HD)",
                    "title": f"{title}{dur_str}",
                    "url": m3u8_url,
                })

        return streams

dailymotion_service = DailymotionService()