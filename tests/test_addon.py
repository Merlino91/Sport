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

if __name__ == "__main__":
    unittest.main()
