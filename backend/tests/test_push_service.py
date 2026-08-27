import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from push_service import NoytrixPushService


class PushServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = NoytrixPushService(Path(self.temp.name), "app", "key")

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_claim_allows_only_one_concurrent_sender(self):
        results = []
        barrier = threading.Barrier(3)

        def claim():
            barrier.wait()
            results.append(self.service.claim_send("same", "title", "body"))

        first = threading.Thread(target=claim)
        second = threading.Thread(target=claim)
        first.start(); second.start(); barrier.wait()
        first.join(); second.join()
        self.assertEqual(sorted(results), [False, True])

    def test_private_push_is_deduplicated_by_semantic_key(self):
        response = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"id": "one"},
        })()
        client = AsyncMock()
        client.__aenter__.return_value.post.return_value = response
        with patch("push_service.httpx.AsyncClient", return_value=client):
            first = asyncio.run(self.service.send_user_push("user", "title", "body", {"dedupe_key": "monthly:2026-07"}))
            second = asyncio.run(self.service.send_user_push("user", "title", "body", {"dedupe_key": "monthly:2026-07"}))
        self.assertEqual(first["id"], "one")
        self.assertTrue(second["skipped"])


if __name__ == "__main__":
    unittest.main()
