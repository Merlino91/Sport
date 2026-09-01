import logging
import urllib.parse
from typing import Any, Dict, List, Optional

logger = logging.getLogger("easysports.replay")

class ReplayService:
    """
    Service responsible for generating and resolving Replay & Highlights streams
    for completed matches (Football, Motor Sports, Tennis, Basketball, etc.).
    All streams are routed through EasyProxy to bypass Geo-blocks and DNS blocks.
    """

    def clean_team_name(self, name: str) -> str:
        """Strips common suffixes and prefixes from team names."""
        for word in ["FC", "CF", "Calcio", "AC", "SS", "AS", "U21", "U23", "BC", "HC"]:
            name = name.replace(f" {word}", "").replace(f"{word} ", "")
        return name.strip()

    def extract_search_terms(self, match: Dict[str, Any]) -> tuple[str, str, str]:
        """Extracts cleaned team names and category from a match object."""
        title = match.get("title", "")
        category = (match.get("category") or "other").lower()

        # Check teams object
        teams = match.get("teams", {})
        home = teams.get("home", {}).get("name", "")
        away = teams.get("away", {}).get("name", "")

        if not home or not away:
            if " vs " in title:
                parts = title.split(" vs ", 1)
                home = parts[0].strip()
                away = parts[1].strip()
            elif " - " in title:
                parts = title.split(" - ", 1)
                home = parts[0].strip()
                away = parts[1].strip()
            else:
                home = title
                away = ""

        return self.clean_team_name(home), self.clean_team_name(away), category

    def build_easyproxy_link(self, ep_url: str, ep_pass: Optional[str], host: str, destination_url: str) -> str:
        """Constructs an EasyProxy extractor stream link."""
        base = ep_url.rstrip("/")
        encoded_d = urllib.parse.quote(destination_url, safe="")
        url = f"{base}/extractor/video.m3u8?host={host}&d={encoded_d}&redirect_stream=true"
        if ep_pass:
            url += f"&api_password={urllib.parse.quote(ep_pass)}"
        return url

    async def get_replays_for_match(
        self,
        match: Dict[str, Any],
        ep_url: str,
        ep_pass: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates structured replay and highlights streams for a completed match.
        Prioritizes Italian official highlights, extended international highlights,
        and full-match halves / full-race replays.
        """
        home, away, category = self.extract_search_terms(match)
        match_title = match.get("title", f"{home} vs {away}")
        replays: List[Dict[str, Any]] = []

        if not ep_url:
            return replays

        # ----------------------------------------------------
        # 1. CALCIO (Football / Soccer)
        # ----------------------------------------------------
        if category in ["football", "soccer"]:
            query_it = urllib.parse.quote(f"{home} {away} highlights sintesi Serie A")
            query_ext = urllib.parse.quote(f"{home} vs {away} extended highlights")
            soccercatch_url = f"https://soccercatch.com/search?q={urllib.parse.quote(home + ' ' + away)}"

            # 🇮🇹 Sintesi Ufficiale Italiana
            replays.append({
                "name": "🇮🇹 Sintesi Ufficiale",
                "title": f"Sintesi in Italiano (Sky / DAZN / Serie A) • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_it}"),
            })

            # 🎬 Highlights Estesi
            replays.append({
                "name": "🎬 Highlights Estesi 1080p",
                "title": f"Sintesi estesa 10-15 min (CBS / TNT Sports) • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_ext}"),
            })

            # ⚽ 1° Tempo Integrale (Replay)
            replays.append({
                "name": "⚽ 1° Tempo Integrale (Full HD)",
                "title": f"Primo Tempo Completo (Full Match Replay) • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "generic", soccercatch_url),
            })

            # ⚽ 2° Tempo Integrale (Replay)
            replays.append({
                "name": "⚽ 2° Tempo Integrale (Full HD)",
                "title": f"Secondo Tempo Completo (Full Match Replay) • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "generic", soccercatch_url),
            })

        # ----------------------------------------------------
        # 2. MOTORI (Motor Sports - F1, MotoGP, Superbike)
        # ----------------------------------------------------
        elif category in ["motor-sports", "motorsport", "f1", "motogp"]:
            query_it = urllib.parse.quote(f"{match_title} sintesi gara Sky Sport")
            query_ext = urllib.parse.quote(f"{match_title} race highlights")
            fullraces_url = f"https://fullraces.com/?s={urllib.parse.quote(match_title)}"

            # 🇮🇹 Sintesi Gara in Italiano
            replays.append({
                "name": "🇮🇹 Sintesi Gara (Sky Sport)",
                "title": f"Highlights con commento italiano • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_it}"),
            })

            # 🏎️ Gara Completa (Full Replay)
            replays.append({
                "name": "🏎️ Gara Completa (Full Race Replay)",
                "title": f"Gara integrale semaforo-bandiera a scacchi • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "generic", fullraces_url),
            })

            # ⏱️ Qualifiche Complete
            replays.append({
                "name": "⏱️ Qualifiche Complete (Replay)",
                "title": f"Sessione di Qualifica integrale • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "generic", fullraces_url),
            })

        # ----------------------------------------------------
        # 3. TENNIS
        # ----------------------------------------------------
        elif category == "tennis":
            query_it = urllib.parse.quote(f"{home} {away} tennis highlights sintesi")
            query_ext = urllib.parse.quote(f"{home} vs {away} match highlights")

            # 🇮🇹 Sintesi Match
            replays.append({
                "name": "🇮🇹 Sintesi Match (SuperTennis/Sky)",
                "title": f"Sintesi punti salienti • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_it}"),
            })

            # 🎬 Highlights Estesi
            replays.append({
                "name": "🎬 Highlights Tennis TV (1080p)",
                "title": f"Sintesi ufficiale punto per punto • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_ext}"),
            })

        # ----------------------------------------------------
        # 4. BASKET (Basketball - NBA, LBA, Euroleague)
        # ----------------------------------------------------
        elif category == "basketball":
            query_it = urllib.parse.quote(f"{home} {away} basket highlights LBA Sky Sport")
            query_ext = urllib.parse.quote(f"{home} vs {away} full game highlights NBA")
            nbareplay_url = f"https://nbahdreplay.com/?s={urllib.parse.quote(home + ' ' + away)}"

            # 🇮🇹 Sintesi Basket
            replays.append({
                "name": "🇮🇹 Sintesi Basket (Sky/LBA)",
                "title": f"Sintesi e azioni spettacolari • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_it}"),
            })

            # 🏀 Full Game Replay (4 Quarti)
            replays.append({
                "name": "🏀 Partita Integrale (Full Game Replay)",
                "title": f"Registrazione completa 4 quarti HD • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "generic", nbareplay_url),
            })

        # ----------------------------------------------------
        # 5. ALTRI SPORT (Rugby, Boxe, Baseball, Hockey, etc.)
        # ----------------------------------------------------
        else:
            query_it = urllib.parse.quote(f"{home} {away} sintesi highlights")
            query_ext = urllib.parse.quote(f"{home} vs {away} full match highlights")

            replays.append({
                "name": "🇮🇹 Sintesi & Highlights",
                "title": f"Highlights e momenti clou • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_it}"),
            })
            replays.append({
                "name": "🎬 Extended Highlights (1080p)",
                "title": f"Extended match recap • {match_title}",
                "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", f"https://www.youtube.com/results?search_query={query_ext}"),
            })

        return replays

replay_service = ReplayService()
