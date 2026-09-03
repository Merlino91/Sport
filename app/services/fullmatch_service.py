import asyncio
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.fullmatch")

class FullMatchService:
    """
    Indexes and extracts full match replay streams (1st half, 2nd half, full match)
    from video hosts supported by EasyProxy (Filemoon, Doodstream, Fastream, etc.).
    """

    def __init__(self):
        # Known replay aggregators accessible via DoH
        self._sources = [
            {
                "name": "footyfull",
                "search_url": "https://footyfull.com/?s={query}",
                "base_url": "https://footyfull.com",
            },
            {
                "name": "fullmatches",
                "search_url": "https://fullmatchesandshows.com/?s={query}",
                "base_url": "https://fullmatchesandshows.com",
            },
        ]
        # Regex for extractable video hosts in EasyProxy
        self._embed_pattern = re.compile(
            r'https?://(?:www\.)?'
            r'(filemoon\.(?:sx|to|in|wf)|'
            r'dood\.(?:to|watch|so|ws|la|pm)|doodstream\.com|'
            r'fastream\.(?:to|org)|'
            r'streamwish\.(?:to|com)|'
            r'supervideo\.(?:cc|tv))'
            r'/[^\s"\'<>]+',
            re.IGNORECASE,
        )

    def extract_team_tokens(self, title: str) -> List[str]:
        """Extracts significant search tokens representing teams from match title."""
        cleaned = re.sub(r'\[.*?\]', '', title)  # remove [Football] prefix if present
        for sep in [" vs ", " vs. ", " - ", " v "]:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                t1 = re.sub(r'[^\w\s]', '', parts[0]).strip()
                t2 = re.sub(r'[^\w\s]', '', parts[1]).strip()
                return [t1, t2]

        return [cleaned.strip()]

    async def find_replay_page_urls(self, team1: str, team2: str) -> List[str]:
        """Searches aggregator sites for article pages matching the two teams."""
        found_urls = []
        query = f"{team1} vs {team2}"
        encoded_q = urllib.parse.quote_plus(query)

        for src in self._sources:
            search_url = src["search_url"].format(query=encoded_q)
            try:
                # Use DoH client to bypass local ISP DNS blocks
                data, _ = await doh_client.get_raw(search_url, timeout=5.0)
                if not data:
                    continue

                html = data.decode("utf-8", errors="ignore")
                # Look for article link matching both teams
                links = re.findall(r'href=[\'"](https?://[^\'"]+)[\'"]', html)
                t1_lower = team1.lower()
                t2_lower = team2.lower()

                for link in links:
                    link_lower = link.lower()
                    if t1_lower in link_lower and t2_lower in link_lower:
                        if link not in found_urls and not link.endswith((".jpg", ".png", ".webp", "/feed/")):
                            found_urls.append(link)
                            if len(found_urls) >= 3:
                                break
            except Exception as e:
                logger.debug("Replay search on %s failed: %s", src["name"], e)

        return found_urls

    async def extract_embeds_from_page(self, page_url: str) -> List[Dict[str, str]]:
        """Scrapes video embed URLs from a match replay article page."""
        results = []
        try:
            data, _ = await doh_client.get_raw(page_url, timeout=6.0)
            if not data:
                return []

            html = data.decode("utf-8", errors="ignore")
            # Find iframe or direct embed links
            embeds = self._embed_pattern.findall(html)
            # Find full URLs matching pattern
            matches = [m.group(0) for m in self._embed_pattern.finditer(html)]

            # Deduplicate preserving order
            seen = set()
            for u in matches:
                clean_url = u.rstrip("\\/.,'\"")
                if clean_url in seen:
                    continue
                seen.add(clean_url)

                # Determine period: 1st half or 2nd half
                label = "▶️ Partita Integrale"
                context_idx = html.find(clean_url)
                if context_idx != -1:
                    snippet = html[max(0, context_idx - 300): context_idx + 100].lower()
                    if "1st" in snippet or "first" in snippet or "1 tempo" in snippet or "1st half" in snippet:
                        label = "⏪ 1° Tempo Integrale"
                    elif "2nd" in snippet or "second" in snippet or "2 tempo" in snippet or "2nd half" in snippet:
                        label = "⏩ 2° Tempo Integrale"

                results.append({"label": label, "embed_url": clean_url})
        except Exception as e:
            logger.debug("Failed extracting embeds from %s: %s", page_url, e)

        return results

    async def get_replay_streams(
        self,
        match_title: str,
        ep_url: str,
        ep_pass: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extracts full match video streams and wraps them into EasyProxy URLs for Stremio.
        """
        teams = self.extract_team_tokens(match_title)
        if len(teams) < 2:
            return []

        team1, team2 = teams[0], teams[1]
        page_urls = await self.find_replay_page_urls(team1, team2)
        if not page_urls:
            return []

        from app.services.stream_service import stream_service

        all_embeds = []
        for url in page_urls[:2]:
            embeds = await self.extract_embeds_from_page(url)
            all_embeds.extend(embeds)
            if len(all_embeds) >= 4:
                break

        streams = []
        for item in all_embeds:
            embed_url = item["embed_url"]
            label = item["label"]
            host = stream_service.detect_host(embed_url)
            proxy_url = stream_service.build_easyproxy_url(ep_url, ep_pass, host, embed_url)

            host_label = host.capitalize()
            streams.append({
                "name": f"{label} ({host_label})",
                "title": f"Replay integrale via EasyProxy",
                "url": proxy_url,
            })

        return streams

fullmatch_service = FullMatchService()