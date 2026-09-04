import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import time
import asyncio
from app.services.db_service import DBService
from app.services.dailymotion_service import dailymotion_service
from app.services.fullmatch_service import fullmatch_service
from app.services.stream_service import stream_service

class ReplayAndRecapTestCase(unittest.TestCase):

    def setUp(self):
        # Use an isolated in-memory or temp SQLite database for tests
        self.test_db_path = Path(__file__).parent / "test_events.db"
        self.db = DBService(db_path=self.test_db_path)

    def tearDown(self):
        # Cleanup test db
        if self.test_db_path.exists():
            try:
                self.test_db_path.unlink()
            except Exception:
                pass

    def test_db_service_retention_and_purge(self):
        now_ms = int(time.time() * 1000)
        matches = [
            # 1. Live match (date in 1 hour)
            {"id": "match-live", "title": "Real Madrid vs Barcelona", "category": "football", "date": now_ms + 3600000},
            # 2. Concluded 10 hours ago (within 72h window)
            {"id": "match-10h", "title": "Juventus vs Milan", "category": "football", "date": now_ms - (10 * 3600 * 1000)},
            # 3. Concluded 80 hours ago (beyond 72h window)
            {"id": "match-80h", "title": "Inter vs Napoli", "category": "football", "date": now_ms - (80 * 3600 * 1000)},
        ]

        self.db.upsert_matches(matches)

        # Retrieve concluded matches within 72h
        concluded = self.db.get_concluded_matches(category_id="football", max_age_hours=72)
        concluded_ids = [m["id"] for m in concluded]
        self.assertIn("match-10h", concluded_ids)
        self.assertNotIn("match-live", concluded_ids)
        self.assertNotIn("match-80h", concluded_ids)

        # Purge older than 72 hours
        purged_count = self.db.purge_expired_matches(max_age_hours=72)
        self.assertEqual(purged_count, 1)

        # Match 80h is now completely gone
        self.assertIsNone(self.db.get_match_by_id("match-80h"))
        # Match 10h is still present
        self.assertIsNotNone(self.db.get_match_by_id("match-10h"))

    def test_dailymotion_query_cleaning(self):
        self.assertEqual(
            dailymotion_service.clean_search_query("Juventus vs Milan"),
            "Juventus Milan highlights"
        )
        self.assertEqual(
            dailymotion_service.clean_search_query("Inter - Atalanta"),
            "Inter Atalanta highlights"
        )

    def test_fullmatch_team_token_extraction(self):
        tokens = fullmatch_service.extract_team_tokens("[Football] Arsenal vs Chelsea")
        self.assertEqual(tokens, ["Arsenal", "Chelsea"])

        tokens2 = fullmatch_service.extract_team_tokens("Liverpool - Manchester City")
        self.assertEqual(tokens2, ["Liverpool", "Manchester City"])

    def test_concluded_match_stream_resolution(self):
        # When a match is concluded, get_streams_for_event should query replay sources
        now_ms = time.time() * 1000
        concluded_match = {
            "id": "match-test-replay",
            "title": "Juventus vs Milan",
            "category": "football",
            "date": now_ms - (5 * 3600 * 1000),  # 5 hours ago
            "sources": [],
        }
        # Insert into db_service
        from app.services.db_service import db_service
        db_service.upsert_matches([concluded_match])

        # Test resolving streams for this concluded match
        streams = asyncio.run(
            stream_service.get_streams_for_event(
                item_id="all:match-test-replay",
                ep_url="https://ep.example.com",
                ep_pass="testpass",
            )
        )
        self.assertTrue(len(streams) >= 1)
        # Should either return Dailymotion highlights or the status card
        first_stream = streams[0]
        self.assertTrue("Sintesi" in first_stream["name"] or "Concluso" in first_stream["name"])

    def test_youtube_query_cleaning(self):
        from app.services.youtube_service import youtube_service
        self.assertEqual(
            youtube_service.clean_search_query("Juventus vs Milan"),
            "Juventus Milan highlights"
        )
        self.assertEqual(
            youtube_service.clean_search_query("[Soccer] Inter - Atalanta"),
            "Inter Atalanta highlights"
        )

    def test_youtube_highlight_streams(self):
        from app.services.youtube_service import youtube_service
        streams = asyncio.run(youtube_service.get_highlight_streams("Juventus vs Milan"))
        self.assertTrue(len(streams) >= 1)
        self.assertIn("ytId", streams[0])
        self.assertTrue(len(streams[0]["ytId"]) == 11)
        self.assertIn("YouTube", streams[0]["name"])

    def test_dailymotion_ondemand_url_generation(self):
        streams = asyncio.run(
            dailymotion_service.get_highlight_streams("Juventus vs Milan", base_url="https://easysports.example.com")
        )
        if streams:
            first = streams[0]
            self.assertIn("https://easysports.example.com/dailymotion/stream/", first["url"])
            self.assertTrue(first["url"].endswith(".m3u8"))
            self.assertIn("Dailymotion", first["name"])

    def test_dailymotion_endpoint_via_client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/dailymotion/stream/invalid_dummy_vid_123.m3u8")
        self.assertIn(resp.status_code, [404, 502, 307])

    def test_youtube_endpoint_via_client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/youtube/stream/I9LBnO7-6PM.m3u8", follow_redirects=False)
        self.assertEqual(resp.status_code, 307)
        location = resp.headers.get("location", "")
        self.assertTrue("googlevideo.com" in location or "youtube.com" in location)

if __name__ == "__main__":
    unittest.main()
