import asyncio
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
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

    def _extract_master_m3u8_sync(self, video_id: str) -> Optional[str]:
        """Synchronous yt-dlp master HLS playlist generation executed in threadpool."""
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": False,
                "source_address": "0.0.0.0",
                "socket_timeout": 8,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                formats = info.get("formats", [])

                # 1. Best video HLS stream
                video_formats = [f for f in formats if f.get("protocol") == "m3u8_native" and f.get("vcodec") != "none"]
                video_formats.sort(key=lambda x: x.get("height") or x.get("width") or 0, reverse=True)
                f_video = video_formats[0] if video_formats else None

                # 2. Best audio HLS stream
                audio_formats = [f for f in formats if f.get("protocol") == "m3u8_native" and f.get("vcodec") == "none"]
                audio_formats.sort(key=lambda x: x.get("tbr") or x.get("abr") or 0, reverse=True)
                f_audio = audio_formats[0] if audio_formats else None

                if f_video and f_audio:
                    v_url = f_video["url"]
                    a_url = f_audio["url"]
                    res = f_video.get("resolution") or f"{f_video.get('width', 1920)}x{f_video.get('height', 1080)}"
                    master_m3u8 = (
                        "#EXTM3U\n"
                        "#EXT-X-VERSION:3\n"
                        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Main Audio",DEFAULT=YES,AUTOSELECT=YES,URI="{a_url}"\n'
                        f'#EXT-X-STREAM-INF:BANDWIDTH=4500000,RESOLUTION={res},AUDIO="audio"\n'
                        f"{v_url}\n"
                    )
                    return master_m3u8

                # Fallback to direct single HLS if available
                if f_video:
                    return f_video["url"]
        except Exception as e:
            logger.warning("yt-dlp stream extraction failed for %s: %s", video_id, e)
        return None

    async def resolve_stream_manifest(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns (content_str, redirect_url). If content_str is provided, serve it directly.
        """
        res = await asyncio.to_thread(self._extract_master_m3u8_sync, video_id)
        if not res:
            return None, None
        if res.startswith("#EXTM3U"):
            return res, None
        return None, res

    async def resolve_stream_url(self, video_id: str) -> Optional[str]:
        """Backward compatibility for direct stream resolution."""
        content, redirect = await self.resolve_stream_manifest(video_id)
        return redirect or None

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
