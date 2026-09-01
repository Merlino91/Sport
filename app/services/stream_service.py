import logging
import urllib.parse
from typing import Any, Dict, List, Optional
from app.services.streamed_api import streamed_api

logger = logging.getLogger("easysports.stream")

# Flag mappings for languages
LANGUAGE_FLAGS = {
    "english": "🇬🇧",
    "en": "🇬🇧",
    "uk": "🇬🇧",
    "usa": "🇺🇸",
    "us": "🇺🇸",
    "italian": "🇮🇹",
    "italy": "🇮🇹",
    "it": "🇮🇹",
    "spanish": "🇪🇸",
    "spain": "🇪🇸",
    "es": "🇪🇸",
    "french": "🇫🇷",
    "france": "🇫🇷",
    "fr": "🇫🇷",
    "german": "🇩🇪",
    "germany": "🇩🇪",
    "de": "🇩🇪",
    "portuguese": "🇵🇹",
    "brazil": "🇧🇷",
    "pt": "🇵🇹",
    "canada": "🇨🇦",
    "ca": "🇨🇦",
    "dutch": "🇳🇱",
    "nl": "🇳🇱",
    "arabic": "🇸🇦",
    "ar": "🇸🇦",
}

class StreamService:
    """Resolves sports stream sources and generates EasyProxy formatted URLs."""

    def detect_host(self, embed_url: str) -> str:
        """Detects the appropriate EasyProxy extractor host from the embed URL."""
        url_lower = embed_url.lower()
        if "embed.st" in url_lower or "embedstream" in url_lower:
            return "embedst"
        elif "cdnlivetv.tv" in url_lower or "cdnlive" in url_lower:
            return "cdnlive"
        elif "vixsrc" in url_lower:
            return "vixsrc"
        elif "dlstreams" in url_lower:
            return "dlstreams"
        elif "freeshot" in url_lower:
            return "freeshot"
        elif "streamhg" in url_lower:
            return "streamhg"
        elif "sports99" in url_lower:
            return "sports99"
        elif "sportsonline" in url_lower:
            return "sportsonline"
        elif "livetv" in url_lower:
            return "livetv"
        elif "fastream" in url_lower:
            return "fastream"
        elif "vavoo" in url_lower:
            return "vavoo"
        elif "dood" in url_lower:
            return "doodstream"
        elif "filemoon" in url_lower:
            return "filemoon"
        elif "mixdrop" in url_lower:
            return "mixdrop"
        elif "supervideo" in url_lower:
            return "supervideo"
        return "generic"

    def get_flag_for_language(self, lang_text: str) -> str:
        """Finds flag emoji for a given language/channel string."""
        lang_lower = lang_text.lower()
        for key, flag in LANGUAGE_FLAGS.items():
            if key in lang_lower:
                return flag
        return ""

    def build_easyproxy_url(self, ep_url: str, ep_pass: Optional[str], host: str, destination_url: str) -> str:
        """
        Builds the target EasyProxy extractor URL:
        {ep_url}/extractor/video.m3u8?host={host}&d={url_encoded}&redirect_stream=true[&api_password={ep_pass}]
        """
        base = ep_url.rstrip("/")
        encoded_d = urllib.parse.quote(destination_url, safe="")
        url = f"{base}/extractor/video.m3u8?host={host}&d={encoded_d}&redirect_stream=true"
        if ep_pass:
            url += f"&api_password={urllib.parse.quote(ep_pass)}"
        return url

    async def get_streams_for_event(
        self,
        item_id: str,
        ep_url: Optional[str],
        ep_pass: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Resolves streams for an event ID and formats them for Stremio.
        """
        if not ep_url:
            return [
                {
                    "name": "EasySports Configuration Required",
                    "title": "Please configure your EasyProxy URL in the addon settings.",
                    "url": "https://github.com/realbestia1/EasyProxy",
                }
            ]

        # Extract slug/ID
        if ":" in item_id:
            _, slug_id = item_id.split(":", 1)
        else:
            slug_id = item_id

        match = await streamed_api.find_match_by_slug_and_id(slug_id)
        if not match:
            return [{"name": "No streams available", "url": ""}]

        sources = match.get("sources", [])
        streams_result: List[Dict[str, Any]] = []

        for src in sources:
            source_name = src.get("source")
            source_id = src.get("id")
            if not source_name or not source_id:
                continue

            raw_streams = await streamed_api.get_streams_for_source(source_name, source_id)
            for s in raw_streams:
                embed_url = s.get("embedUrl")
                if not embed_url:
                    continue

                lang = s.get("language", "Stream")
                is_hd = s.get("hd", False)
                quality = "HD" if is_hd else "SD"
                flag = self.get_flag_for_language(lang)

                name_parts = []
                if flag:
                    name_parts.append(flag)
                name_parts.append(quality)
                stream_name = " ".join(name_parts)

                host = self.detect_host(embed_url)
                proxy_stream_url = self.build_easyproxy_url(ep_url, ep_pass, host, embed_url)

                stream_item = {
                    "name": stream_name,
                    "url": proxy_stream_url,
                }
                if lang and lang != "Stream":
                    stream_item["description"] = lang

                streams_result.append(stream_item)

        if not streams_result:
            return [{"name": "No streams available", "url": ""}]

        return streams_result

stream_service = StreamService()
