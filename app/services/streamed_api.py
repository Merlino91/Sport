import logging
import time
from typing import Any, Dict, List, Optional
from app.config import STREAMED_API_HOST, STREAMED_CACHE_TTL
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.streamed")

class StreamedAPI:
    """
    Client for the Streamed sports events and streams API.
    Caches match lists to avoid overloading upstream API.
    """

    def __init__(self):
        self._matches_cache: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0
        self._base_host = STREAMED_API_HOST

    async def get_all_matches(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Returns all matches, using in-memory cache if fresh."""
        now = time.time()
        if not force_refresh and self._matches_cache and (now - self._cache_timestamp < STREAMED_CACHE_TTL):
            return self._matches_cache

        url = f"https://{self._base_host}/api/matches/all"
        data = await doh_client.get_json(url, host_header=self._base_host)
        if isinstance(data, list):
            self._matches_cache = data
            self._cache_timestamp = now
            logger.info("Loaded %d matches from Streamed API", len(data))
            return data

        # Fallback to existing cache if refresh failed
        if self._matches_cache:
            logger.warning("Upstream refresh failed, using stale cache (%d items)", len(self._matches_cache))
            return self._matches_cache

        return []

    async def get_streams_for_source(self, source: str, source_id: str) -> List[Dict[str, Any]]:
        """
        Fetches the stream list for a given match source.
        Endpoint: /api/stream/{source}/{source_id}
        """
        url = f"https://{self._base_host}/api/stream/{source}/{source_id}"
        data = await doh_client.get_json(url, host_header=self._base_host)
        if isinstance(data, list):
            return data
        return []

    async def find_match_by_slug_and_id(self, slug_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Finds a match in the match list by full ID (e.g. 'cincinnati-reds-vs-san-diego-padres-2388957')
        or numeric/suffix ID.
        """
        matches = await self.get_all_matches()
        # Direct ID match
        for m in matches:
            if m.get("id") == slug_or_id:
                return m

        # Match by ending ID number or substring
        for m in matches:
            mid = str(m.get("id", ""))
            if mid.endswith(slug_or_id) or slug_or_id in mid:
                return m

        return None

streamed_api = StreamedAPI()
