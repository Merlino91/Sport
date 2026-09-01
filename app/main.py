import base64
import json
import logging
from pathlib import Path
from typing import Optional, Tuple
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    ADDON_DESCRIPTION,
    ADDON_ID,
    ADDON_NAME,
    ADDON_VERSION,
    DISCIPLINE_CATALOGS,
    ID_PREFIXES,
)
from app.services.catalog_service import catalog_service
from app.services.doh_client import doh_client
from app.services.stream_service import stream_service

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("easysports")

# Directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="EasySports Stremio Addon", version=ADDON_VERSION)

# Enable CORS for all origins (required by Stremio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def decode_config(config_str: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Decodes the Base64 config path parameter.
    Format: 'epUrl|epPass|tz' (or JSON fallback).
    Returns (ep_url, ep_pass, tz).
    """
    if not config_str:
        return None, None, "UTC"

    try:
        # Restore base64 padding
        b64 = config_str.replace("-", "+").replace("_", "/")
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        raw = base64.b64decode(b64).decode("utf-8")

        # Pipe delimited format: epUrl|epPass|tz
        if "|" in raw:
            parts = raw.split("|")
            ep_url = parts[0].strip() if len(parts) > 0 else None
            ep_pass = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            tz = parts[2].strip() if len(parts) > 2 and parts[2].strip() else "UTC"
            return ep_url, ep_pass, tz

        # Fallback to JSON format
        data = json.loads(raw)
        return data.get("epUrl"), data.get("epPass"), data.get("tz", "UTC")
    except Exception as e:
        logger.debug("Failed decoding config '%s': %s", config_str, e)
        return None, None, "UTC"


def get_base_url(request: Request) -> str:
    """
    Extracts the correct public base URL respecting reverse proxy headers
    (X-Forwarded-Proto, X-Forwarded-Host from Traefik/Dokploy/Cloudflare).
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    
    # Remove standard ports if present
    if proto == "https" and host.endswith(":443"):
        host = host[:-4]
    elif proto == "http" and host.endswith(":80"):
        host = host[:-3]
        
    return f"{proto}://{host}".rstrip("/")


def build_manifest(configured: bool = False) -> dict:
    """Builds the Stremio Addon manifest."""
    catalogs = []
    for c in DISCIPLINE_CATALOGS:
        catalogs.append({
            "type": "Live Sports",
            "id": c["id"],
            "name": c["name"],
            "extra": [{"name": "search", "isRequired": False}],
        })

    return {
        "id": ADDON_ID,
        "version": ADDON_VERSION,
        "name": ADDON_NAME,
        "description": ADDON_DESCRIPTION,
        "types": ["Live Sports", "channel"],
        "resources": ["catalog", "meta", "stream"],
        "idPrefixes": ID_PREFIXES,
        "catalogs": catalogs,
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": not configured,
        },
    }


# ==========================================
# Web Configuration Routes
# ==========================================

@app.get("/", response_class=HTMLResponse)
@app.get("/configure", response_class=HTMLResponse)
async def configure_page(
    request: Request,
    epUrl: Optional[str] = None,
    epPass: Optional[str] = None,
    tz: Optional[str] = None,
    save: Optional[str] = None,
):
    """Renders the configuration Web UI."""
    install_url = None
    stremio_url = None

    if save and epUrl:
        # Encode config: epUrl|epPass|tz
        ep_pass_clean = epPass or ""
        tz_clean = tz or "UTC"
        raw_config = f"{epUrl.strip()}|{ep_pass_clean.strip()}|{tz_clean.strip()}"
        encoded_config = base64.b64encode(raw_config.encode("utf-8")).decode("utf-8")
        
        # Build URLs with correct public scheme and host
        base_url = get_base_url(request)
        install_url = f"{base_url}/{encoded_config}/manifest.json"
        stremio_url = install_url.replace("http://", "stremio://").replace("https://", "stremio://")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "disciplines": DISCIPLINE_CATALOGS,
            "epUrl": epUrl or "",
            "epPass": epPass or "",
            "tz": tz or "",
            "install_url": install_url,
            "stremio_url": stremio_url,
            "configured": bool(install_url),
        },
    )


# ==========================================
# Stremio Addon Protocol Routes
# ==========================================

@app.get("/manifest.json")
async def unconfigured_manifest():
    """Unconfigured manifest route."""
    return JSONResponse(content=build_manifest(configured=False))


@app.get("/{config}/manifest.json")
async def configured_manifest(config: str):
    """Configured manifest route."""
    ep_url, _, _ = decode_config(config)
    is_configured = bool(ep_url)
    return JSONResponse(content=build_manifest(configured=is_configured))


@app.get("/{config}/catalog/{type}/{id}.json")
@app.get("/{config}/catalog/{type}/{id}/{extra}.json")
async def catalog_endpoint(request: Request, config: str, type: str, id: str, extra: Optional[str] = None):
    """Catalog endpoint returning live sports matches for a discipline."""
    _, _, user_tz = decode_config(config)
    base_url = get_base_url(request)

    search_query = None
    if extra:
        # Stremio formats extra params as 'search=foo' or 'skip=0'
        if extra.startswith("search="):
            search_query = extra.split("search=", 1)[1]

    items = await catalog_service.get_catalog(id, search=search_query, user_tz=user_tz, base_url=base_url)
    return JSONResponse(content={"metas": items})


@app.get("/{config}/meta/{type}/{id}.json")
async def meta_endpoint(request: Request, config: str, type: str, id: str):
    """Meta detail endpoint for a specific match card."""
    _, _, user_tz = decode_config(config)
    base_url = get_base_url(request)
    meta = await catalog_service.get_meta_detail(id, user_tz=user_tz, base_url=base_url)
    if not meta:
        raise HTTPException(status_code=404, detail="Meta not found")
    return JSONResponse(content={"meta": meta})


@app.get("/image-proxy")
async def image_proxy_endpoint(url: str):
    """Proxies poster/background images through DoH client to bypass ISP/DNS blocks."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    target_url = url.strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = f"https://{STREAMED_API_HOST}{target_url if target_url.startswith('/') else '/' + target_url}"

    content, content_type = await doh_client.get_raw(target_url)
    if not content:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=content,
        media_type=content_type or "image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/{config}/stream/{type}/{id}.json")
async def stream_endpoint(config: str, type: str, id: str):
    """Stream resolution endpoint returning EasyProxy-wrapped stream links."""
    ep_url, ep_pass, user_tz = decode_config(config)
    streams = await stream_service.get_streams_for_event(id, ep_url=ep_url, ep_pass=ep_pass, user_tz=user_tz)
    return JSONResponse(content={"streams": streams})


@app.get("/health")
async def health_check():
    """Service health check."""
    return {"status": "ok", "addon": ADDON_NAME, "version": ADDON_VERSION}

