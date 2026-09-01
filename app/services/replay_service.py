import asyncio
import httpx
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

logger = logging.getLogger("easysports.replay")

class ReplayService:
    """
    Service that searches and resolves REAL video streams for completed matches.
    Uses YouTube InnerTube public API to fetch real highlight videos, titles, and durations,
    and wraps them in EasyProxy extractor stream URLs.
    """

    def __init__(self):
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._http_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
        }

    def clean_team_name(self, name: str) -> str:
        """Strips common suffixes and prefixes from team names."""
        for word in ["FC", "CF", "Calcio", "AC", "SS", "AS", "U21", "U23", "BC", "HC", "S.p.A."]:
            name = name.replace(f" {word}", "").replace(f"{word} ", "")
        return name.strip()

    def extract_search_terms(self, match: Dict[str, Any]) -> tuple[str, str, str]:
        """Extracts cleaned team names and category from a match object."""
        title = match.get("title", "")
        category = (match.get("category") or "other").lower()

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
        """Constructs a valid EasyProxy extractor stream link."""
        base = ep_url.rstrip("/")
        encoded_d = urllib.parse.quote(destination_url, safe="")
        url = f"{base}/extractor/video.m3u8?host={host}&d={encoded_d}&redirect_stream=true"
        if ep_pass:
            url += f"&api_password={urllib.parse.quote(ep_pass)}"
        return url

    async def search_youtube_innertube(self, query: str, max_results: int = 4) -> List[Dict[str, Any]]:
        """
        Searches YouTube using InnerTube API and returns structured video items.
        """
        url = "https://www.youtube.com/youtubei/v1/search"
        payload = {
            "context": {
                "client": {
                    "hl": "it",
                    "gl": "IT",
                    "clientName": "WEB",
                    "clientVersion": "2.20230515.00.00",
                }
            },
            "query": query
        }

        try:
            async with httpx.AsyncClient(headers=self._http_headers, timeout=6.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    sections = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
                    results = []
                    for sec in sections:
                        items = sec.get("itemSectionRenderer", {}).get("contents", [])
                        for it in items:
                            if "videoRenderer" in it:
                                vr = it["videoRenderer"]
                                vid = vr.get("videoId")
                                title_runs = vr.get("title", {}).get("runs", [])
                                title = "".join(r.get("text", "") for r in title_runs)
                                length = vr.get("lengthText", {}).get("simpleText", "")
                                channel = "".join(r.get("text", "") for r in vr.get("ownerText", {}).get("runs", []))
                                if vid:
                                    results.append({
                                        "videoId": vid,
                                        "title": title,
                                        "duration": length,
                                        "channel": channel,
                                        "url": f"https://www.youtube.com/watch?v={vid}"
                                    })
                                    if len(results) >= max_results:
                                        return results
                    return results
        except Exception as e:
            logger.warning("InnerTube YouTube search failed for '%s': %s", query, e)

        return []

    async def get_replays_for_match(
        self,
        match: Dict[str, Any],
        ep_url: str,
        ep_pass: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Resolves real video streams for a concluded match.
        """
        if not ep_url:
            return []

        match_id = match.get("id", "")
        if match_id in self._cache:
            return self._cache[match_id]

        home, away, category = self.extract_search_terms(match)
        match_title = match.get("title", f"{home} vs {away}")
        replays: List[Dict[str, Any]] = []

        # ----------------------------------------------------
        # 1. CALCIO (Football)
        # ----------------------------------------------------
        if category in ["football", "soccer"]:
            query_it = f"{home} {away} highlights Serie A sintesi"
            query_ext = f"{home} vs {away} extended highlights"

            videos_it, videos_ext = await asyncio.gather(
                self.search_youtube_innertube(query_it, max_results=3),
                self.search_youtube_innertube(query_ext, max_results=2),
                return_exceptions=True
            )

            seen_vids = set()

            if isinstance(videos_it, list):
                for idx, v in enumerate(videos_it):
                    if v["videoId"] not in seen_vids:
                        seen_vids.add(v["videoId"])
                        dur = f" ({v['duration']})" if v.get("duration") else ""
                        channel = f" • {v['channel']}" if v.get("channel") else ""
                        replays.append({
                            "name": f"🇮🇹 Sintesi #{idx+1}{dur}",
                            "title": f"{v['title']}{channel}",
                            "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                            "behaviorHints": {"notWebReady": False}
                        })

            if isinstance(videos_ext, list):
                for idx, v in enumerate(videos_ext):
                    if v["videoId"] not in seen_vids:
                        seen_vids.add(v["videoId"])
                        dur = f" ({v['duration']})" if v.get("duration") else ""
                        replays.append({
                            "name": f"🎬 Extended Highlights #{idx+1}{dur}",
                            "title": f"{v['title']}",
                            "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                            "behaviorHints": {"notWebReady": False}
                        })

        # ----------------------------------------------------
        # 2. MOTORI (F1, MotoGP)
        # ----------------------------------------------------
        elif category in ["motor-sports", "motorsport", "f1", "motogp"]:
            query = f"{match_title} gara sintesi Sky Sport F1 highlights"
            videos = await self.search_youtube_innertube(query, max_results=4)
            for idx, v in enumerate(videos):
                dur = f" ({v['duration']})" if v.get("duration") else ""
                channel = f" • {v['channel']}" if v.get("channel") else ""
                label = f"🏎️ Sintesi Gara #{idx+1}{dur}"
                replays.append({
                    "name": label,
                    "title": f"{v['title']}{channel}",
                    "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                    "behaviorHints": {"notWebReady": False}
                })

        # ----------------------------------------------------
        # 3. TENNIS
        # ----------------------------------------------------
        elif category == "tennis":
            query = f"{home} {away} tennis highlights sintesi"
            videos = await self.search_youtube_innertube(query, max_results=4)
            for idx, v in enumerate(videos):
                dur = f" ({v['duration']})" if v.get("duration") else ""
                replays.append({
                    "name": f"🎾 Highlights Match #{idx+1}{dur}",
                    "title": f"{v['title']}",
                    "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                    "behaviorHints": {"notWebReady": False}
                })

        # ----------------------------------------------------
        # 4. BASKET (Basketball)
        # ----------------------------------------------------
        elif category == "basketball":
            query = f"{home} {away} basket highlights LBA NBA"
            videos = await self.search_youtube_innertube(query, max_results=4)
            for idx, v in enumerate(videos):
                dur = f" ({v['duration']})" if v.get("duration") else ""
                replays.append({
                    "name": f"🏀 Sintesi Basket #{idx+1}{dur}",
                    "title": f"{v['title']}",
                    "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                    "behaviorHints": {"notWebReady": False}
                })

        # ----------------------------------------------------
        # 5. ALTRI SPORT
        # ----------------------------------------------------
        else:
            query = f"{match_title} highlights recap"
            videos = await self.search_youtube_innertube(query, max_results=4)
            for idx, v in enumerate(videos):
                dur = f" ({v['duration']})" if v.get("duration") else ""
                replays.append({
                    "name": f"🎬 Highlights #{idx+1}{dur}",
                    "title": f"{v['title']}",
                    "url": self.build_easyproxy_link(ep_url, ep_pass, "youtube", v["url"]),
                    "behaviorHints": {"notWebReady": False}
                })

        if replays:
            self._cache[match_id] = replays

        return replays

replay_service = ReplayService()
