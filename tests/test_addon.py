import unittest
import base64
from fastapi.testclient import TestClient
from app.main import app, decode_config, get_base_url
from app.services.stream_service import stream_service
from app.services.catalog_service import catalog_service

client = TestClient(app)

class EasySportsCleanTestCase(unittest.TestCase):

    def test_decode_config_pipe(self):
        # Format: epUrl|epPass|tz
        raw = "https://ep.example.com|mypass|Europe/Rome"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        ep_url, ep_pass, tz = decode_config(encoded)
        self.assertEqual(ep_url, "https://ep.example.com")
        self.assertEqual(ep_pass, "mypass")
        self.assertEqual(tz, "Europe/Rome")

    def test_decode_config_empty(self):
        ep_url, ep_pass, tz = decode_config(None)
        self.assertIsNone(ep_url)
        self.assertIsNone(ep_pass)
        self.assertEqual(tz, "UTC")

    def test_unconfigured_manifest(self):
        response = client.get("/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "com.easysports.addon")
        self.assertTrue(data["behaviorHints"]["configurationRequired"])
        self.assertEqual(len(data["catalogs"]), 16)

    def test_configured_manifest(self):
        raw = "https://ep.example.com|pass|Europe/Rome"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        response = client.get(f"/{encoded}/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["behaviorHints"]["configurationRequired"])

    def test_health_check(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_status_card_future_match(self):
        import time
        now_ms = time.time() * 1000
        future_match = {
            "id": "test-future-123",
            "title": "Juventus vs Milan",
            "date": now_ms + (120 * 60 * 1000),  # 2 hours in the future
        }
        cards = stream_service.generate_status_card(future_match, user_tz="Europe/Rome")
        self.assertEqual(len(cards), 1)
        self.assertTrue("⏳ Inizia tra" in cards[0]["name"])
        self.assertTrue(cards[0]["behaviorHints"]["notWebReady"])

    def test_status_card_finished_match(self):
        import time
        now_ms = time.time() * 1000
        finished_match = {
            "id": "test-past-123",
            "title": "Inter vs Atalanta",
            "date": now_ms - (4 * 3600 * 1000),  # 4 hours ago
        }
        cards = stream_service.generate_status_card(finished_match, user_tz="Europe/Rome")
        self.assertEqual(len(cards), 1)
        self.assertTrue("🏁 Evento Terminato" in cards[0]["name"])

    def test_live_stream_easyproxy_url_generation(self):
        ep_url = "https://ep.myproxy.com"
        ep_pass = "secret123"
        embed_url = "https://embed.st/stream/test1234"
        host = stream_service.detect_host(embed_url)
        self.assertEqual(host, "embedst")

        proxy_url = stream_service.build_easyproxy_url(ep_url, ep_pass, host, embed_url)
        self.assertTrue(proxy_url.startswith("https://ep.myproxy.com/extractor/video.m3u8"))
        self.assertIn("host=embedst", proxy_url)
        self.assertIn("api_password=secret123", proxy_url)
        self.assertIn("redirect_stream=true", proxy_url)

    def test_image_proxy_routing(self):
        base_url = "https://easysports.myvps.com"
        sample_image_path = "/api/images/proxy/abc123xyz.webp"
        proxied = catalog_service.normalize_image_url(sample_image_path, base_url=base_url)
        self.assertTrue(proxied.startswith("https://easysports.myvps.com/image-proxy?url="))

    def test_configure_page(self):
        response = client.get("/configure")
        self.assertEqual(response.status_code, 200)
        self.assertIn("EasySports", response.text)

    def test_configure_save(self):
        response = client.get("/configure?save=1&epUrl=https%3A%2F%2Fep.bluccoj.com&epPass=Z3r0EP&tz=Europe%2FRome")
        self.assertEqual(response.status_code, 200)
        self.assertIn("manifest.json", response.text)

if __name__ == "__main__":
    unittest.main()
