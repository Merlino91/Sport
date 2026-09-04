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

    def _extract_m3u8_sync(self, video_id: str) -> Optional[str]:
        """Synchronous yt-dlp extraction executed in threadpool."""
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
                "socket_timeout": 8,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                formats = info.get("formats", [])
                # Prefer 1080p or 720p HLS m3u8_native stream
                hls_formats = [f for f in formats if "m3u8" in f.get("protocol", "")]
                if hls_formats:
                    hls_formats.sort(key=lambda x: x.get("height") or 0, reverse=True)
                    return hls_formats[0].get("url")
                # Fallback to direct MP4 progressive download URL
                mp4_formats = [f for f in formats if f.get("ext") == "mp4" and f.get("url")]
                if mp4_formats:
                    mp4_formats.sort(key=lambda x: x.get("height") or 0, reverse=True)
                    return mp4_formats[0].get("url")
        except Exception as e:
            logger.warning("yt-dlp stream extraction failed for %s: %s", video_id, e)
        return None

    async def resolve_stream_url(self, video_id: str) -> Optional[str]:
        """
        Asynchronously resolves a direct playable HLS (.m3u8) or MP4 URL for YouTube.
        """
        return await asyncio.to_thread(self._extract_m3u8_sync, video_id)

    async def get_highlight_streams(self, match_title: str, base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns a Stremio stream item configured with direct on-demand .m3u8 resolver
        and native 'ytId' parameter for maximum compatibility across all devices.
        """
        video = await self.search_highlight_video(match_title)
        if not video or not video.get("video_id"):
            return []

        vid_id = video["video_id"]
        title = video.get("title", f"{match_title} Highlights")

        endpoint_path = f"/youtube/stream/{vid_id}.m3u8"
        stream_url = f"{base_url.rstrip('/')}{endpoint_path}" if base_url else endpoint_path
        yt_watch_url = f"https://www.youtube.com/watch?v={vid_id}"

        return [
            {
                "name": "🎬 Sintesi Ufficiale (YouTube HD)",
                "title": f"{title} (1080p)",
                "ytId": vid_id,
                "url": stream_url,
                "externalUrl": yt_watch_url,
            }
        ]

youtube_service = YouTubeService()
