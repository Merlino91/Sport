import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
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

    async def get_highlight_streams(self, match_title: str, base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Searches for highlight videos matching the match title and returns
        Stremio-compatible stream dictionaries pointing to our on-demand resolver.
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

            # Route to our on-demand endpoint which generates the fresh token at click-time
            endpoint_path = f"/dailymotion/stream/{vid_id}.m3u8"
            stream_url = f"{base_url.rstrip('/')}{endpoint_path}" if base_url else endpoint_path

            streams.append({
                "name": "🎬 Sintesi & Gol (Dailymotion)",
                "title": f"{title}{dur_str}",
                "url": stream_url,
            })

        return streams

    async def resolve_and_proxy_manifest(self, video_id: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Resolves fresh master .m3u8 URL at the exact moment of playback
        and fetches the manifest content using browser session headers.
        Returns (content_bytes, media_type, target_url).
        """
        m3u8_url = await self.get_stream_m3u8(video_id)
        if not m3u8_url:
            return None, None, None

        # Fetch the live manifest content with browser headers to avoid hotlink blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.dailymotion.com/",
            "Origin": "https://www.dailymotion.com",
        }

        try:
            data, content_type = await doh_client.get_raw(m3u8_url, custom_headers=headers, timeout=8.0)
            if data:
                return data, content_type or "application/vnd.apple.mpegurl", m3u8_url
        except Exception as e:
            logger.warning("Manifest proxy fetch failed for video %s: %s", video_id, e)

        # Fallback to redirect URL
        return None, "application/vnd.apple.mpegurl", m3u8_url

dailymotion_service = DailymotionService()
