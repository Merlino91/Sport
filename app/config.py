import os

# Server configuration
HOST = os.getenv("EASYSPORTS_HOST", "0.0.0.0")
PORT = int(os.getenv("EASYSPORTS_PORT", "7001"))
DEBUG = os.getenv("EASYSPORTS_DEBUG", "false").lower() in ("true", "1", "yes")

# Upstream API settings
STREAMED_API_HOST = os.getenv("STREAMED_API_HOST", "streamed.pk")
STREAMED_FALLBACK_HOSTS = ["streamed.su", "streamed.pk"]
STREAMED_DOH_RESOLVER = "https://cloudflare-dns.com/dns-query"
STREAMED_CACHE_TTL = int(os.getenv("STREAMED_CACHE_TTL", "60"))  # seconds

# Addon Metadata
ADDON_ID = "com.easysports.addon"
ADDON_NAME = "EasySports"
ADDON_VERSION = "1.0.0"
ADDON_DESCRIPTION = "Live sports events and streams, organized by discipline. Configure your playback proxy in the panel."

# Disciplines supported by Streamed and EasySports
DISCIPLINE_CATALOGS = [
    {"id": "all", "name": "All Sports"},
    {"id": "basketball", "name": "Basketball"},
    {"id": "football", "name": "Football"},
    {"id": "american-football", "name": "American Football"},
    {"id": "hockey", "name": "Hockey"},
    {"id": "baseball", "name": "Baseball"},
    {"id": "motor-sports", "name": "Motor Sports"},
    {"id": "fight", "name": "Fight (UFC, Boxing)"},
    {"id": "tennis", "name": "Tennis"},
    {"id": "rugby", "name": "Rugby"},
    {"id": "golf", "name": "Golf"},
    {"id": "billiards", "name": "Billiards"},
    {"id": "afl", "name": "AFL"},
    {"id": "darts", "name": "Darts"},
    {"id": "cricket", "name": "Cricket"},
    {"id": "other", "name": "Other"},
]

ID_PREFIXES = [f"{c['id']}:" for c in DISCIPLINE_CATALOGS]
