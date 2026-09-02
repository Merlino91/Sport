import logging
import time
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

    def generate_status_card(self, match: Optional[Dict[str, Any]], user_tz: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generates an informative placeholder card with countdown or match status."""
        if not match:
            return [{
                "name": "Nessun flusso disponibile",
                "title": "Evento non trovato o rimosso dai provider.",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]

        date_ms = match.get("date", 0)
        if not date_ms:
            return [{
                "name": "Nessun flusso attivo",
                "title": "Nessuna sorgente video attiva al momento. Riprova più tardi.",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]

        now_ms = time.time() * 1000
        diff_mins = int((date_ms - now_ms) / 60000)

        # Format localized start time
        from app.services.catalog_service import catalog_service
        start_time_str = catalog_service.format_event_date(date_ms, user_tz)

        if diff_mins > 1440:
            days = diff_mins // 1440
            hours = (diff_mins % 1440) // 60
            time_left = f"{days}g {hours}h" if hours else f"{days} giorni"
            return [{
                "name": f"⏳ Inizia tra {time_left}",
                "title": f"Inizio: {start_time_str} • I flussi saranno disponibili 20 minuti prima dell'inizio",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]
        elif diff_mins > 60:
            hours = diff_mins // 60
            mins = diff_mins % 60
            time_left = f"{hours}h {mins}m" if mins else f"{hours}h"
            return [{
                "name": f"⏳ Inizia tra {time_left}",
                "title": f"Inizio: {start_time_str} • I flussi saranno disponibili 20 minuti prima dell'inizio",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]
        elif diff_mins > 20:
            return [{
                "name": f"⏳ Inizia tra ~{diff_mins} min",
                "title": f"Inizio: {start_time_str} • I flussi saranno disponibili 20 minuti prima dell'inizio",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]
        elif diff_mins > 0:
            return [{
                "name": "⏳ Inizio imminente (Caricamento flussi)",
                "title": f"Inizio: {start_time_str} • I flussi sono in fase di attivazione sui server, riprova a breve",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]
        elif diff_mins >= -180:
            return [{
                "name": "🔴 Partita in corso (Nessun flusso)",
                "title": f"Iniziata alle {start_time_str} • Nessuna sorgente attiva al momento",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]
        else:
            return [{
                "name": "🏁 Evento Terminato",
                "title": f"Questa partita si è conclusa (iniziata il {start_time_str})",
                "url": "https://www.google.com",
                "behaviorHints": {"notWebReady": True},
            }]

    async def get_streams_for_event(
        self,
        item_id: str,
        ep_url: Optional[str],
        ep_pass: Optional[str] = None,
        user_tz: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Resolves streams for an event ID and formats them for Stremio.
        Enforces time-window rules: hides streams until 20 min before start,
        and marks concluded matches as finished.
        """
        if not ep_url:
            return [
                {
                    "name": "Configurazione Richiesta",
                    "title": "Configura l'URL del tuo EasyProxy nel pannello dell'addon.",
                    "url": "https://github.com/realbestia1/EasyProxy",
                    "behaviorHints": {"notWebReady": True},
                }
            ]

        # Extract slug/ID
        if ":" in item_id:
            _, slug_id = item_id.split(":", 1)
        else:
            slug_id = item_id

        match = await streamed_api.find_match_by_slug_and_id(slug_id)
        if not match:
            return self.generate_status_card(None, user_tz)

        # Time-window check: hide streams if > 20 min before start or show Evento Terminato if > 3h after start
        date_ms = match.get("date", 0)
        if date_ms:
            now_ms = time.time() * 1000
            diff_mins = int((date_ms - now_ms) / 60000)

            # More than 20 min before start -> show countdown card
            if diff_mins > 20:
                return self.generate_status_card(match, user_tz)

            # More than 3 hours after start -> show Evento Terminato card
            if diff_mins < -180:
                return self.generate_status_card(match, user_tz)

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
            return self.generate_status_card(match, user_tz)

        return streams_result

stream_service = StreamService()
