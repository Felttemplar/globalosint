from contextlib import closing
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from globalosint.database import connect, initialize
from globalosint.freshrss import FreshRSSError, FreshRSSClient, sync_freshrss


class FakeClient:
    def __init__(self, items):
        self.items = items

    def subscriptions(self):
        return [{"id": "feed/7", "title": "Agência de teste", "url": "https://feeds.example.org/rss.xml"}]

    def entries(self, max_items=500, since_hours=24):
        return self.items[:max_items]


def item(article_id="one", published=None):
    return {
        "id": article_id,
        "title": "Relato de teste",
        "published": published if published is not None else int(time.time()) - 60,
        "alternate": [{"href": "https://news.example.org/story/1"}],
        "summary": {"content": "<p>Texto &amp; contexto.</p>"},
        "origin": {"streamId": "feed/7"},
    }


class FreshRSSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rss.sqlite3"
        self.env = patch.dict(os.environ, {"GLOBALOSINT_DB_PATH": str(self.path)})
        self.env.start()
        initialize()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_sync_registers_candidate_and_deduplicates_without_creating_events(self):
        result = sync_freshrss(FakeClient([item(), item("different-id")]))
        self.assertEqual((1, 1, 2), (result["imported"], result["duplicates"], result["records_seen"]))
        with closing(connect()) as db:
            source = db.execute("SELECT status,name FROM sources").fetchone()
            observation = db.execute("SELECT title,summary,review_status FROM source_items").fetchone()
            events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual("candidate", source["status"])
        self.assertEqual("Agência de teste", source["name"])
        self.assertEqual("Relato de teste", observation["title"])
        self.assertEqual("Texto & contexto.", observation["summary"])
        self.assertEqual("unreviewed", observation["review_status"])
        self.assertEqual(0, events)

    def test_items_outside_window_are_skipped(self):
        old = int(time.time()) - 25 * 3600
        result = sync_freshrss(FakeClient([item("old", old)]), since_hours=24)
        self.assertEqual(1, result["skipped"])
        self.assertEqual(0, result["imported"])

    def test_api_url_requires_https_except_loopback(self):
        with self.assertRaises(FreshRSSError):
            FreshRSSClient("http://feeds.example.org/api/greader.php", "user", "password")
        client = FreshRSSClient("http://localhost:8080/api/greader.php", "user", "password")
        self.assertEqual("http://localhost:8080/api/greader.php", client.api_url)

    def test_client_logs_in_and_reads_subscription_and_articles(self):
        class Response:
            def __init__(self, body):
                self.body = body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit=-1):
                return self.body

        calls = []
        def opener(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/accounts/ClientLogin"):
                return Response(b"SID=session\nAuth=api-token\n")
            if "/subscription/list?" in request.full_url:
                return Response(json.dumps({"subscriptions": []}).encode())
            return Response(json.dumps({"items": [item()], "continuation": None}).encode())

        client = FreshRSSClient("https://feeds.example.org/api/greader.php", "user", "password", opener=opener)
        self.assertEqual([], client.subscriptions())
        self.assertEqual(1, len(client.entries(max_items=10)))
        self.assertEqual(3, len(calls))
        self.assertIn("GoogleLogin auth=api-token", calls[1].get_header("Authorization"))
        self.assertIn("ot=", calls[2].full_url)


if __name__ == "__main__":
    unittest.main()
