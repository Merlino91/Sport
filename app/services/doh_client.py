import logging
import ssl
import time
import httpx
from typing import Dict, Optional, Tuple

logger = logging.getLogger("easysports.doh")

class DoHClient:
    """
    HTTP Client with built-in DNS-over-HTTPS resolution to bypass local/ISP DNS blocks.
    Caches resolved IP addresses and performs direct HTTPS requests with correct Host header & SNI.
    """

    def __init__(self):
        self._dns_cache: Dict[str, Tuple[str, float]] = {}  # hostname -> (ip, expire_time)
        self._doh_endpoints = [
            "https://cloudflare-dns.com/dns-query",
            "https://dns.google/resolve",
        ]
        # Insecure SSL context for cases where upstream cert CN doesn't match raw IP during custom SNI routing
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    async def resolve(self, hostname: str) -> Optional[str]:
        """Resolves hostname to IPv4 using DoH resolvers with TTL caching."""
        now = time.time()
        if hostname in self._dns_cache:
            ip, expire_at = self._dns_cache[hostname]
            if now < expire_at:
                return ip

        async with httpx.AsyncClient(timeout=5.0) as client:
            for endpoint in self._doh_endpoints:
                try:
                    params = {"name": hostname, "type": "A"}
                    headers = {"accept": "application/dns-json"}
                    res = await client.get(endpoint, params=params, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        answers = data.get("Answer", [])
                        for ans in answers:
                            if ans.get("type") == 1 and "data" in ans:
                                ip = ans["data"]
                                ttl = ans.get("TTL", 300)
                                self._dns_cache[hostname] = (ip, now + min(ttl, 600))
                                logger.debug("DoH resolved %s -> %s (TTL: %ds)", hostname, ip, ttl)
                                return ip
                except Exception as e:
                    logger.warning("DoH lookup via %s failed for %s: %s", endpoint, hostname, e)

        return None

    async def get_json(self, url: str, host_header: Optional[str] = None, timeout: float = 10.0) -> Optional[dict]:
        """
        Executes an HTTP GET request resolving host via DoH when necessary.
        """
        parsed = httpx.URL(url)
        hostname = parsed.host

        resolved_ip = await self.resolve(hostname)
        target_url = url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        if resolved_ip and resolved_ip != hostname:
            # Replace hostname with resolved IP in URL and set Host header
            target_url = str(parsed.copy_with(host=resolved_ip))
            headers["Host"] = host_header or hostname

        transport = httpx.AsyncHTTPTransport(verify=self._ssl_context)
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            try:
                response = await client.get(target_url, headers=headers)
                if response.status_code == 200:
                    return response.json()
                logger.warning("Request to %s returned status %d", url, response.status_code)
            except Exception as e:
                logger.error("Failed requesting %s: %s", url, e)

        return None

doh_client = DoHClient()
