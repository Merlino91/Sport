import datetime
import logging
import urllib.parse
from typing import Any, Dict, List, Optional
import pytz
from app.config import DISCIPLINE_CATALOGS, STREAMED_API_HOST
from app.services.streamed_api import streamed_api

logger = logging.getLogger("easysports.catalog")

# Category mapping normalization
CATEGORY_MAP = {
    "all": "all",
    "basketball": "basketball",
    "football": "football",
    "american-football": "american-football",
    "hockey": "hockey",
    "baseball": "baseball",
    "motor-sports": "motor-sports",
    "fight": "fight",
    "tennis": "tennis",
    "rugby": "rugby",
    "golf": "golf",
    "billiards": "billiards",
    "afl": "afl",
    "darts": "darts",
    "cricket": "cricket",
    "other": "other",
}

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

        desc_parts = [formatted_date, title]
        if is_popular:
            desc_parts.append("⭐ Popular")
        description = " • ".join(desc_parts)

        stremio_id = f"{category_id}:{match_id}"

        item = {
            "id": stremio_id,
            "type": "Live Sports",
            "name": display_name,
            "posterShape": "landscape",
            "description": description,
            "genres": [discipline_label],
            "releaseInfo": formatted_date,
        }

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
        """Returns the list of meta items for a requested discipline catalog."""
        matches = await streamed_api.get_all_matches()
        items = []

        for m in matches:
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

        match = await streamed_api.find_match_by_slug_and_id(slug_id)
        if not match:
            return None

        meta = self.build_meta_item(match, category_id, user_tz, base_url=base_url)
        return meta

catalog_service = CatalogService()
