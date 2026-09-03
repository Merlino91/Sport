import datetime
import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional
import pytz
from app.config import DISCIPLINE_CATALOGS, STREAMED_API_HOST
from app.services.db_service import db_service
from app.services.streamed_api import streamed_api

logger = logging.getLogger("easysports.catalog")

DISCIPLINE_TITLES = {c["id"]: c["name"] for c in DISCIPLINE_CATALOGS}

class CatalogService:
    """Builds Stremio Catalog and Meta objects from Streamed events."""

    def format_event_date(self, timestamp_ms: int, user_tz: Optional[str] = None) -> str:
        """Converts timestamp in ms to localized date string (e.g. '1 Sept 2026, 21:00')."""
        try:
            tz = pytz.timezone(user_tz or "UTC")
        except Exception:
            tz = pytz.UTC

        dt_utc = datetime.datetime.fromtimestamp(timestamp_ms / 1000, tz=datetime.timezone.utc)
        dt_local = dt_utc.astimezone(tz)
        # Format: e.g. "1 Sep 2026, 20:45"
        return dt_local.strftime("%d %b %Y, %H:%M").lstrip("0")

    def normalize_image_url(self, path: Optional[str], base_url: Optional[str] = None) -> Optional[str]:
        """Ensures image URL is routed through addon image proxy to bypass DNS blocks."""
        if not path:
            return None
        if not path.startswith("http://") and not path.startswith("https://"):
            full_url = f"https://{STREAMED_API_HOST}{path}"
        else:
            full_url = path

        if base_url:
            encoded = urllib.parse.quote(full_url, safe="")
            return f"{base_url}/image-proxy?url={encoded}"

        return full_url

    def build_meta_item(
        self,
        match: Dict[str, Any],
        category_id: str,
        user_tz: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Converts a raw match object into a Stremio meta preview object."""
        match_id = match.get("id", "")
        title = match.get("title", "Live Sports")
        match_category = match.get("category", "other")
        date_ms = match.get("date", 0)
        formatted_date = self.format_event_date(date_ms, user_tz) if date_ms else "Live"
        is_popular = match.get("popular", False)

        poster_url = self.normalize_image_url(match.get("poster"), base_url=base_url)
        discipline_label = DISCIPLINE_TITLES.get(category_id, DISCIPLINE_TITLES.get(match_category, "Live Sports"))

        # Formatted title and description
        if category_id == "all":
            display_name = f"[{discipline_label}] {title}"
        else:
            display_name = title

        is_live = False
        is_concluded = False
        now_ms = time.time() * 1000

        if not date_ms:
            is_live = True
            formatted_date = "Live"
            desc_parts = ["LIVE NOW"]
            if is_popular:
                desc_parts.append("⭐ Popular")
            description = " • ".join(desc_parts)
        else:
            formatted_date = self.format_event_date(date_ms, user_tz)
            diff_mins = int((date_ms - now_ms) / 60000)

            if diff_mins < -240:
                is_concluded = True
                desc_parts = [formatted_date, title, "🏁 Conclusa • Replay e Sintesi"]
            else:
                desc_parts = [formatted_date, title]
                if is_popular:
                    desc_parts.append("⭐ Popular")
                if diff_mins <= 0:
                    is_live = True

            description = " • ".join(desc_parts)

        stremio_id = f"{category_id}:{match_id}"

        item = {
            "id": stremio_id,
            "type": "Live Sports",
            "name": display_name,
            "posterShape": "landscape",
            "description": description,
            "genres": [discipline_label],
            "releaseInfo": formatted_date if not is_concluded else f"🏁 {formatted_date}",
        }

        if is_live:
            item["directorInfo"] = {"status": "LIVE"}

        if poster_url:
            item["poster"] = poster_url
            item["background"] = poster_url

        return item

    async def get_catalog(
        self,
        category_id: str,
        search: Optional[str] = None,
        user_tz: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns the list of meta items for a requested discipline catalog.
        Combines current/upcoming matches with concluded matches from the past 72 hours.
        """
        matches = await streamed_api.get_all_matches()
        if matches:
            db_service.upsert_matches(matches)

        # Retrieve concluded matches from local store (last 72 hours)
        concluded_matches = db_service.get_concluded_matches(category_id=category_id, max_age_hours=72)

        # Merge active matches and concluded matches without duplicates
        active_ids = {str(m.get("id")) for m in matches if m.get("id")}
        all_matches = list(matches)
        for cm in concluded_matches:
            if str(cm.get("id")) not in active_ids:
                all_matches.append(cm)

        items = []
        for m in all_matches:
            m_cat = (m.get("category") or "other").lower()

            # Filter by category
            if category_id != "all" and m_cat != category_id:
                continue

            # Filter by search query if provided
            if search:
                title = m.get("title", "").lower()
                if search.lower() not in title:
                    continue

            items.append(self.build_meta_item(m, category_id, user_tz, base_url=base_url))

        return items

    async def get_meta_detail(
        self,
        item_id: str,
        user_tz: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Returns the detailed meta object for an event."""
        # item_id format: "category:slug-id" or "slug-id"
        if ":" in item_id:
            category_id, slug_id = item_id.split(":", 1)
        else:
            category_id, slug_id = "all", item_id

        # First check active matches from upstream API
        match = await streamed_api.find_match_by_slug_and_id(slug_id)
        # Fallback to local 72h store for concluded matches
        if not match:
            match = db_service.get_match_by_id(slug_id)

        if not match:
            return None

        meta = self.build_meta_item(match, category_id, user_tz, base_url=base_url)
        return meta

catalog_service = CatalogService()
