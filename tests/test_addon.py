import base64
import unittest
from fastapi.testclient import TestClient
from app.main import app, decode_config
from app.services.catalog_service import catalog_service
from app.services.stream_service import stream_service

class EasySportsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_decode_config(self):
        # Test pipe format: epUrl|epPass|tz
        raw = "https://ep.example.com|mySecretPass|Europe/Rome"
        b64 = base64.b64encode(raw.encode()).decode()
        url, pwd, tz = decode_config(b64)
        self.assertEqual(url, "https://ep.example.com")
        self.assertEqual(pwd, "mySecretPass")
        self.assertEqual(tz, "Europe/Rome")

        # Test empty / None
        url, pwd, tz = decode_config(None)
        self.assertIsNone(url)
        self.assertEqual(tz, "UTC")

    def test_unconfigured_manifest(self):
        response = self.client.get("/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "com.easysports.addon")
        self.assertIn("catalogs", data)
        self.assertGreater(len(data["catalogs"]), 0)
        self.assertTrue(data["behaviorHints"]["configurationRequired"])

    def test_configured_manifest(self):
        raw = "https://ep.example.com|pass|Europe/Rome"
        b64 = base64.b64encode(raw.encode()).decode()
        response = self.client.get(f"/{b64}/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["behaviorHints"]["configurationRequired"])

    def test_stream_service_url_builder(self):
        ep_url = "https://ep.example.com"
        ep_pass = "secret123"
        embed_url = "https://embed.st/embed/admin/test-match/1"
        host = stream_service.detect_host(embed_url)
        self.assertEqual(host, "embedst")

        proxy_url = stream_service.build_easyproxy_url(ep_url, ep_pass, host, embed_url)
        self.assertIn("https://ep.example.com/extractor/video.m3u8", proxy_url)
        self.assertIn("host=embedst", proxy_url)
        self.assertIn("api_password=secret123", proxy_url)
        self.assertIn("redirect_stream=true", proxy_url)

    def test_catalog_date_formatting(self):
        timestamp = 1788228600000
        formatted_utc = catalog_service.format_event_date(timestamp, "UTC")
        formatted_rome = catalog_service.format_event_date(timestamp, "Europe/Rome")
        self.assertGreater(len(formatted_utc), 5)
        self.assertGreater(len(formatted_rome), 5)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_configure_page_rendering(self):
        response = self.client.get("/configure")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sports addon for", response.text)
        self.assertIn("Proxy URL", response.text)

    def test_configure_submission(self):
        response = self.client.get("/configure?save=1&epUrl=https%3A%2F%2Fep.bluccoj.com&epPass=Z3r0EP&tz=Europe%2FRome")
        self.assertEqual(response.status_code, 200)
        self.assertIn("stremio://", response.text)
        self.assertIn("manifest.json", response.text)

    def test_image_proxy_url_rewriting(self):
        sample_path = "/api/images/proxy/test.webp"
        proxied_url = catalog_service.normalize_image_url(sample_path, base_url="https://mysports.com")
        self.assertIn("https://mysports.com/image-proxy?url=", proxied_url)
        self.assertIn("streamed.pk", proxied_url)

    def test_stream_time_window_cards(self):
        import time
        now_ms = time.time() * 1000
        
        # Match 2 hours in the future (> 20 min)
        future_match = {"id": "test-future", "date": now_ms + 7200000}
        card_future = stream_service.generate_status_card(future_match, "Europe/Rome")
        self.assertTrue(any("⏳" in c["name"] for c in card_future))
        self.assertTrue(card_future[0]["behaviorHints"]["notWebReady"])

        # Match 4 hours in the past (< -180 min)
        ended_match = {"id": "test-ended", "date": now_ms - 14400000}
        card_ended = stream_service.generate_status_card(ended_match, "Europe/Rome")
        self.assertTrue(any("🏁" in c["name"] for c in card_ended))

    def test_replay_service_generation(self):
        import asyncio
        from app.services.replay_service import replay_service
        
        sample_football_match = {
            "id": "torino-vs-monza-2577931",
            "title": "Torino vs Monza",
            "category": "football",
            "teams": {"home": {"name": "Torino FC"}, "away": {"name": "Monza"}},
        }
        replays = asyncio.run(replay_service.get_replays_for_match(sample_football_match, ep_url="https://ep.example.com", ep_pass="pass"))
        self.assertGreater(len(replays), 0)
        self.assertTrue(any("🇮🇹" in r["name"] for r in replays))
        self.assertTrue(any("1° Tempo" in r["name"] for r in replays))
        self.assertTrue(all("https://ep.example.com/extractor/video.m3u8" in r["url"] for r in replays))

    def test_streamed_api_history_pruning(self):
        import time
        from app.services.streamed_api import streamed_api, HISTORY_RETENTION_MS
        now_ms = time.time() * 1000
        
        test_matches = [
            {"id": "fresh-1", "title": "Fresh Match", "date": now_ms - 3600000},
            {"id": "old-1", "title": "Very Old Match", "date": now_ms - (HISTORY_RETENTION_MS + 10000000)},
        ]
        merged = streamed_api._prune_and_merge(test_matches)
        merged_ids = [m["id"] for m in merged]
        self.assertIn("fresh-1", merged_ids)
        self.assertNotIn("old-1", merged_ids)

if __name__ == "__main__":
    unittest.main()
