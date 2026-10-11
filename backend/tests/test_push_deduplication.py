import asyncio
import hashlib
import tempfile
import unittest
import uuid
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

if "httpx" not in sys.modules:
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = object
    sys.modules["httpx"] = httpx_stub

from push_service import NoytrixPushService


class PushDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = NoytrixPushService(Path(self.temp_dir.name), "app-id", "api-key")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_claim_is_atomic_for_same_logical_push(self):
        self.assertTrue(self.service.claim_send("same", "Title", "Body"))
        self.assertFalse(self.service.claim_send("same", "Title", "Body"))

    def test_provider_key_is_stable_rfc_uuid(self):
        first = self.service.provider_idempotency_key("logical-operation")
        second = self.service.provider_idempotency_key("logical-operation")
        self.assertEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)

    def test_private_push_deduplicates_and_sends_provider_key(self):
        response = type("Response", (), {"status_code": 200, "raise_for_status": lambda self: None, "json": lambda self: {"id": "sent"}})()
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with patch("push_service.httpx.AsyncClient", return_value=client):
            first = asyncio.run(self.service.send_user_push("user-1", "Title", "Body", {"dedupe_key": "event-1"}))
            second = asyncio.run(self.service.send_user_push("user-1", "Title", "Body", {"dedupe_key": "event-1"}))
        self.assertEqual(first["id"], "sent")
        self.assertTrue(second["skipped"])
        self.assertEqual(client.post.await_count, 1)
        payload = client.post.await_args.kwargs["json"]
        private_key = hashlib.sha256(b"user:user-1:event-1").hexdigest()
        self.assertEqual(payload["idempotency_key"], self.service.provider_idempotency_key(private_key))
        self.assertEqual(str(uuid.UUID(payload["idempotency_key"])), payload["idempotency_key"])


if __name__ == "__main__":
    unittest.main()
