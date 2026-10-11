import unittest
import sys
import types

if "httpx" not in sys.modules:
    class _HttpxClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = _HttpxClient
    httpx_stub.Timeout = lambda *args, **kwargs: None
    httpx_stub.TimeoutException = TimeoutError
    sys.modules["httpx"] = httpx_stub

from scamshield.url_intel.safe_http import (
    UnsafeTargetError,
    fetch_public_url,
    is_public_ip,
    validate_public_url,
    verify_peer_ip,
)


class _PeerStream:
    def __init__(self, peer):
        self.peer = peer

    def get_extra_info(self, key):
        return (self.peer, 443) if key in {"server_addr", "peername"} else None


class _Response:
    def __init__(self, status, peer, body=b"", headers=None, encoding="utf-8"):
        self.status_code = status
        self.extensions = {"network_stream": _PeerStream(peer)}
        self.headers = headers or {}
        self.encoding = encoding
        self.body = body

    async def aiter_bytes(self):
        yield self.body


class _ResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return False


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def stream(self, method, url, headers=None):
        self.requests.append((method, url, headers))
        return _ResponseContext(self.responses.pop(0))


class UrlNetworkSafetyTests(unittest.TestCase):
    def test_blocks_loopback_and_private_dns(self):
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"):
            with self.subTest(ip=ip), self.assertRaises(UnsafeTargetError) as ctx:
                validate_public_url("https://example.test", resolver=lambda _host, _port, value=ip: [value])
            self.assertEqual(ctx.exception.code, "non_public_ip")

    def test_blocks_credentials_and_unsafe_ports(self):
        with self.assertRaises(UnsafeTargetError) as credentials:
            validate_public_url("https://user:pass@example.com", resolver=lambda *_: ["93.184.216.34"])
        self.assertEqual(credentials.exception.code, "userinfo_not_allowed")
        with self.assertRaises(UnsafeTargetError) as port:
            validate_public_url("http://example.com:8080", resolver=lambda *_: ["93.184.216.34"])
        self.assertEqual(port.exception.code, "port_not_allowed")

    def test_accepts_only_public_resolution(self):
        target = validate_public_url("HTTPS://Example.COM/path#fragment", resolver=lambda *_: ["93.184.216.34"])
        self.assertEqual(target.url, "https://example.com/path")
        self.assertTrue(is_public_ip("93.184.216.34"))

    def test_mixed_public_and_private_dns_is_blocked(self):
        with self.assertRaises(UnsafeTargetError):
            validate_public_url("https://example.com", resolver=lambda *_: ["93.184.216.34", "127.0.0.1"])

    def test_peer_must_match_validated_dns(self):
        target = validate_public_url("https://example.com", resolver=lambda *_: ["93.184.216.34"])
        self.assertEqual(verify_peer_ip("93.184.216.34", target), "93.184.216.34")
        with self.assertRaises(UnsafeTargetError) as mismatch:
            verify_peer_ip("1.1.1.1", target)
        self.assertEqual(mismatch.exception.code, "dns_peer_mismatch")

    def test_peer_ip_is_required(self):
        target = validate_public_url("https://example.com", resolver=lambda *_: ["93.184.216.34"])
        with self.assertRaises(UnsafeTargetError) as missing:
            verify_peer_ip(None, target)
        self.assertEqual(missing.exception.code, "peer_ip_unavailable")


class SafeFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_validated_public_response(self):
        client = _Client([_Response(200, "93.184.216.34", b"hello", {"content-type": "text/plain"})])
        result = await fetch_public_url(
            "https://example.com",
            resolver=lambda *_: ["93.184.216.34"],
            client=client,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["peer_ip"], "93.184.216.34")

    async def test_redirect_to_metadata_ip_is_blocked_before_request(self):
        client = _Client([
            _Response(302, "93.184.216.34", headers={"location": "http://169.254.169.254/latest/meta-data"})
        ])

        def resolver(host, _port):
            return ["93.184.216.34"] if host == "example.com" else ["169.254.169.254"]

        with self.assertRaises(UnsafeTargetError) as blocked:
            await fetch_public_url("https://example.com", resolver=resolver, client=client)
        self.assertEqual(blocked.exception.code, "non_public_ip")
        self.assertEqual(len(client.requests), 1)

    async def test_response_size_limit_is_enforced(self):
        client = _Client([_Response(200, "93.184.216.34", b"x" * 20)])
        with self.assertRaises(UnsafeTargetError) as large:
            await fetch_public_url(
                "https://example.com",
                resolver=lambda *_: ["93.184.216.34"],
                client=client,
                max_bytes=10,
            )
        self.assertEqual(large.exception.code, "response_too_large")


if __name__ == "__main__":
    unittest.main()
