import os
import sys
import types
import unittest
from unittest.mock import patch

if "httpx" not in sys.modules:
    class _Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = _Client
    httpx_stub.Timeout = lambda *args, **kwargs: None
    httpx_stub.TimeoutException = TimeoutError
    sys.modules["httpx"] = httpx_stub

from scamshield.url_intel.headless_sandbox import analyze_headless_sandbox


class HeadlessTruthfulnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_sandbox_is_unknown_not_safe(self):
        with patch.dict(os.environ, {"NOYTRIX_HEADLESS_SANDBOX": "0"}):
            result = await analyze_headless_sandbox("https://example.test")

        self.assertFalse(result["available"])
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["assessment_status"], "insufficient_data")
        self.assertEqual(result["score"], 0)


if __name__ == "__main__":
    unittest.main()
