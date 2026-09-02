import asyncio
import httpx
import json

async def test_innertube(query: str):
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
        res = await client.post(url, json=payload)
        print(f"InnerTube status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            # Traverse contents
            try:
                sections = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"]
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
                print(f"Found {len(results)} videos for '{query}':")
                for r in results[:4]:
                    print(f"  - [{r['channel']}] {r['title']} ({r['duration']}) -> {r['url']}")
                return results
            except Exception as e:
                print("Error parsing InnerTube response:", e)
    return []

async def main():
    await test_innertube("Torino Monza highlights Serie A")
    await test_innertube("Jannik Sinner Carlos Alcaraz highlights")
    await test_innertube("Formula 1 Monza gara sintesi Sky Sport")

if __name__ == "__main__":
    asyncio.run(main())
