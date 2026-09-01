import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optionalimport json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import STREAMED_API_HOST, STREAMED_CACHE_TTL
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.streamed")

# 72 hours retention in milliseconds
HISTORY_RETENTION_MS = 72 * 3600 * 1000

class StreamedAPI:
    """
    Client for the Streamed sports events and streams API.
    Caches match lists and maintains a 72-hour rolling history of completed matches
    so that recaps and replays remain accessible after matches end.
    """

    def __init__(self):
        self._matches_cache: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0
        self._base_host = STREAMED_API_HOST
        
        # History file storage in app data directory
        self._data_dir = Path(__file__).resolve().parent.parent / "data"
        self._history_file = self._data_dir / "recent_matches.json"
        self._matches_history: Dict[str, Dict[str, Any]] = self._load_history()

    def _load_history(self) -> Dict[str, Dict[str, Any]]:
        """Loads historical matches from local storage or returns initial seed matches."""
        if self._history_file.exists():
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data:
                        return data
            except Exception as e:
                logger.warning("Could not read recent matches history: %s", e)

        # Default initial seed matches for instant testing
        now_ms = int(time.time() * 1000)
        h = 3600 * 1000
        sample_poster = f"https://{self._base_host}/api/images/proxy/GwZg7AZpYEZgHCAjAJgCzrAY29lBWSUYAUwVmDTAE5p5gJhqDh61hh1OPgBDYLKQRcOJBt15cyAE1LBCETI3BiOzKvBoh+1EDiTa9IY1mMgSIXbyOL8wJBSwi5jFGFUoe78o2pzPdvRg7uJiEEA.webp"
        
        return {
            "torino-vs-monza-2577931": {
                "id": "torino-vs-monza-2577931",
                "title": "Torino vs Monza",
                "category": "football",
                "date": now_ms - (6 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Torino"}, "away": {"name": "Monza"}},
                "sources": []
            },
            "inter-vs-atalanta-2577932": {
                "id": "inter-vs-atalanta-2577932",
                "title": "Inter vs Atalanta",
                "category": "football",
                "date": now_ms - (12 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Inter"}, "away": {"name": "Atalanta"}},
                "sources": []
            },
            "f1-gp-monza-gara-2026": {
                "id": "f1-gp-monza-gara-2026",
                "title": "Formula 1 GP Monza - Gara Integrale",
                "category": "motor-sports",
                "date": now_ms - (18 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Ferrari"}, "away": {"name": "Red Bull"}},
                "sources": []
            },
            "jannik-sinner-vs-carlos-alcaraz-2026": {
                "id": "jannik-sinner-vs-carlos-alcaraz-2026",
                "title": "Jannik Sinner vs Carlos Alcaraz",
                "category": "tennis",
                "date": now_ms - (14 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Jannik Sinner"}, "away": {"name": "Carlos Alcaraz"}},
                "sources": []
            },
            "virtus-bologna-vs-olimpia-milano-2026": {
                "id": "virtus-bologna-vs-olimpia-milano-2026",
                "title": "Virtus Bologna vs Olimpia Milano",
                "category": "basketball",
                "date": now_ms - (8 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Virtus Bologna"}, "away": {"name": "Olimpia Milano"}},
                "sources": []
            },
            "ufc-305-main-event-2026": {
                "id": "ufc-305-main-event-2026",
                "title": "UFC 305: Du Plessis vs Adesanya",
                "category": "fight",
                "date": now_ms - (20 * h),
                "poster": sample_poster,
                "popular": True,
                "teams": {"home": {"name": "Du Plessis"}, "away": {"name": "Adesanya"}},
                "sources": []
            }
        }

    def _save_history(self):
        """Persists historical matches to local storage."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._matches_history, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("Could not save recent matches history: %s", e)

    def _prune_and_merge(self, fresh_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges fresh matches with historical completed matches from the last 72 hours,
        pruning entries older than 72 hours.
        """
        now_ms = time.time() * 1000
        cutoff_ms = now_ms - HISTORY_RETENTION_MS

        # Add / update with fresh matches
        for m in fresh_matches:
            mid = m.get("id")
            if mid:
                self._matches_history[mid] = m

        # Prune old matches (< cutoff)
        pruned_history = {}
        for mid, m in self._matches_history.items():
            date_ms = m.get("date", 0)
            # Keep if no date or within last 72 hours or future
            if not date_ms or date_ms >= cutoff_ms:
                pruned_history[mid] = m

        self._matches_history = pruned_history
        self._save_history()

        # Return list sorted chronologically
        merged_list = list(self._matches_history.values())
        merged_list.sort(key=lambda x: x.get("date", 0))
        return merged_list

    async def get_all_matches(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Returns all matches (live, upcoming, and recent completed within 72h)."""
        now = time.time()
        if not force_refresh and self._matches_cache and (now - self._cache_timestamp < STREAMED_CACHE_TTL):
            return self._matches_cache

        url = f"https://{self._base_host}/api/matches/all"
        data = await doh_client.get_json(url, host_header=self._base_host)
        if isinstance(data, list):
            merged = self._prune_and_merge(data)
            self._matches_cache = merged
            self._cache_timestamp = now
            logger.info("Total matches (active + 72h history): %d", len(merged))
            return merged

        # Fallback to existing cache / history
        if self._matches_cache:
            return self._matches_cache

        if self._matches_history:
            return list(self._matches_history.values())

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
        Finds a match in the match list or history by full ID or suffix.
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

from app.config import STREAMED_API_HOST, STREAMED_CACHE_TTL
from app.services.doh_client import doh_client

logger = logging.getLogger("easysports.streamed")

# 72 hours retention in milliseconds
HISTORY_RETENTION_MS = 72 * 3600 * 1000

class StreamedAPI:
    """
    Client for the Streamed sports events and streams API.
    Caches match lists and maintains a 72-hour rolling history of completed matches
    so that recaps and replays remain accessible after matches end.
    """

    def __init__(self):
        self._matches_cache: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0
        self._base_host = STREAMED_API_HOST
        
        # History file storage in app data directory
        self._data_dir = Path(__file__).resolve().parent.parent / "data"
        self._history_file = self._data_dir / "recent_matches.json"
        self._matches_history: Dict[str, Dict[str, Any]] = self._load_history()

    def _load_history(self) -> Dict[str, Dict[str, Any]]:
        """Loads historical matches from local storage."""
        if self._history_file.exists():
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.warning("Could not read recent matches history: %s", e)
        return {}

    def _save_history(self):
        """Persists historical matches to local storage."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._matches_history, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("Could not save recent matches history: %s", e)

    def _prune_and_merge(self, fresh_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges fresh matches with historical completed matches from the last 72 hours,
        pruning entries older than 72 hours.
        """
        now_ms = time.time() * 1000
        cutoff_ms = now_ms - HISTORY_RETENTION_MS

        # Add / update with fresh matches
        for m in fresh_matches:
            mid = m.get("id")
            if mid:
                self._matches_history[mid] = m

        # Prune old matches (< cutoff)
        pruned_history = {}
        for mid, m in self._matches_history.items():
            date_ms = m.get("date", 0)
            # Keep if no date or within last 72 hours or future
            if not date_ms or date_ms >= cutoff_ms:
                pruned_history[mid] = m

        self._matches_history = pruned_history
        self._save_history()

        # Return list sorted chronologically
        merged_list = list(self._matches_history.values())
        merged_list.sort(key=lambda x: x.get("date", 0))
        return merged_list

    async def get_all_matches(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Returns all matches (live, upcoming, and recent completed within 72h)."""
        now = time.time()
        if not force_refresh and self._matches_cache and (now - self._cache_timestamp < STREAMED_CACHE_TTL):
            return self._matches_cache

        url = f"https://{self._base_host}/api/matches/all"
        data = await doh_client.get_json(url, host_header=self._base_host)
        if isinstance(data, list):
            merged = self._prune_and_merge(data)
            self._matches_cache = merged
            self._cache_timestamp = now
            logger.info("Total matches (active + 72h history): %d", len(merged))
            return merged

        # Fallback to existing cache / history
        if self._matches_cache:
            return self._matches_cache

        if self._matches_history:
            return list(self._matches_history.values())

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
        Finds a match in the match list or history by full ID or suffix.
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
