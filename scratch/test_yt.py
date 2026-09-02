import asyncio
import httpx
import re
import sys
import urllib.parse
sys.path.insert(0, ".")

async def search_yt_videos(query: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    # Test Invidious search
    invidious_instances = [
        "https://inv.tux.pizza/api/v1/search",
        "https://invidious.nerdvpn.de/api/v1/search",
        "https://vid.priv.au/api/v1/search",
    ]
    
    async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
        for instance in invidious_instances:
            try:
                res = await client.get(instance, params={"q": query, "type": "video"})
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    for item in data[:3]:
                        vid = item.get("videoId")
                        title = item.get("title")
                        if vid:
                            results.append({"videoId": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}"})
                    if results:
                        print(f"[{instance}] Found {len(results)} videos for '{query}':")
                        for r in results:
                            print(f"  - {r['title']} -> {r['url']}")
                        return results
            except Exception as e:
                pass
    
    # Fallback to DDG search for youtube videos
    try:
        ddg_url = "https://html.duckduckgo.com/html/"
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
            res = await client.post(ddg_url, data={"q": f"site:youtube.com {query}"})
            if res.status_code == 200:
                vids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", res.text)
                seen = set()
                results = []
                for v in vids:
                    if v not in seen:
                        seen.add(v)
                        results.append({"videoId": v, "title": query, "url": f"https://www.youtube.com/watch?v={v}"})
                if results:
                    print(f"[DDG Fallback] Found {len(results)} videos for '{query}':")
                    for r in results[:3]:
                        print(f"  - {r['url']}")
                    return results[:3]
    except Exception as e:
        print("DDG search failed:", e)

    return []

async def main():
    await search_yt_videos("Torino Monza highlights Serie A")
    await search_yt_videos("Jannik Sinner Carlos Alcaraz highlights")
    await search_yt_videos("Formula 1 Monza gara sintesi")

if __name__ == "__main__":
    asyncio.run(main())
