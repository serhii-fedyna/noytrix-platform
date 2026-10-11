from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UnsafeTargetError(ValueError):
    def __init__(self, code: str, message: str, *, url: str | None = None):
        super().__init__(message)
        self.code = code
        self.url = url


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(str(value).split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return bool(address.is_global)
    except ValueError:
        return False


def _default_resolver(host: str, port: int) -> list[str]:
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(answer[4][0]).split("%")[0] for answer in answers})


def validate_public_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[str]] | None = None,
    allowed_ports: set[int] | None = None,
) -> ValidatedTarget:
    raw = str(url or "").strip()
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise UnsafeTargetError("unsupported_scheme", "Only HTTP and HTTPS targets are allowed.", url=raw)
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeTargetError("userinfo_not_allowed", "Credentials in target URLs are not allowed.", url=raw)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if not host:
            raise UnsafeTargetError("missing_host", "Target URL has no host.", url=raw)
        port = parsed.port or (443 if scheme == "https" else 80)
    except UnsafeTargetError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise UnsafeTargetError("invalid_url", "Target URL is invalid.", url=raw) from exc

    if port not in (allowed_ports or ALLOWED_PORTS):
        raise UnsafeTargetError("port_not_allowed", f"Target port {port} is not allowed.", url=raw)

    resolve = resolver or _default_resolver
    try:
        ips = tuple(sorted(set(resolve(host, port))))
    except (OSError, socket.gaierror) as exc:
        raise UnsafeTargetError("dns_resolution_failed", "Target host could not be resolved.", url=raw) from exc
    if not ips:
        raise UnsafeTargetError("dns_no_addresses", "Target host has no resolved IP addresses.", url=raw)

    blocked = [ip for ip in ips if not is_public_ip(ip)]
    if blocked:
        raise UnsafeTargetError("non_public_ip", "Target resolves to non-public network space.", url=raw)

    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port != (443 if scheme == "https" else 80):
        netloc = f"{netloc}:{port}"
    normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return ValidatedTarget(normalized, host, port, ips)


def response_peer_ip(response: Any) -> str | None:
    extensions = getattr(response, "extensions", {}) or {}
    stream = extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        return None
    for key in ("server_addr", "peername"):
        try:
            value = stream.get_extra_info(key)
        except Exception:
            value = None
        if isinstance(value, (tuple, list)) and value:
            return str(value[0]).split("%")[0]
        if isinstance(value, str) and value:
            return value.split("%")[0]
    return None


def verify_peer_ip(peer_ip: str | None, target: ValidatedTarget) -> str:
    if not peer_ip:
        raise UnsafeTargetError("peer_ip_unavailable", "Could not verify the connected peer IP.", url=target.url)
    normalized = str(ipaddress.ip_address(peer_ip.split("%")[0]))
    if not is_public_ip(normalized):
        raise UnsafeTargetError("non_public_peer_ip", "Connected peer is not in public network space.", url=target.url)
    approved = {str(ipaddress.ip_address(ip.split("%")[0])) for ip in target.resolved_ips}
    if normalized not in approved:
        raise UnsafeTargetError("dns_peer_mismatch", "Connected peer does not match the validated DNS result.", url=target.url)
    return normalized


async def fetch_public_url(
    url: str,
    *,
    timeout: float = 12.0,
    max_redirects: int = 5,
    max_bytes: int = 1_500_000,
    headers: dict[str, str] | None = None,
    resolver: Callable[[str, int], list[str]] | None = None,
    client: httpx.AsyncClient | None = None,
    read_body: bool = True,
) -> dict[str, Any]:
    """Fetch an untrusted public URL with validation at every network hop."""
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 6.0)),
            follow_redirects=False,
            verify=True,
            trust_env=False,
            headers=headers or {},
        )

    hops: list[dict[str, Any]] = []
    current = str(url or "").strip()
    try:
        for index in range(max_redirects + 1):
            target = await asyncio.to_thread(validate_public_url, current, resolver=resolver)
            async with client.stream("GET", target.url, headers=headers) as response:
                peer_ip = verify_peer_ip(response_peer_ip(response), target)
                location = response.headers.get("location")
                hop = {
                    "index": index,
                    "url": target.url,
                    "host": target.host,
                    "status_code": int(response.status_code),
                    "peer_ip": peer_ip,
                    "resolved_ips": list(target.resolved_ips),
                    "location": location,
                }
                hops.append(hop)

                if response.status_code in REDIRECT_STATUSES:
                    if not location:
                        raise UnsafeTargetError("redirect_without_location", "Redirect response has no Location header.", url=target.url)
                    if index >= max_redirects:
                        raise UnsafeTargetError("too_many_redirects", "Redirect limit exceeded.", url=target.url)
                    current = urljoin(target.url, location)
                    continue

                chunks: list[bytes] = []
                size = 0
                if read_body:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise UnsafeTargetError("response_too_large", "Response body exceeds the analysis limit.", url=target.url)
                        chunks.append(chunk)
                body = b"".join(chunks)
                encoding = response.encoding or "utf-8"
                text = body.decode(encoding, errors="replace")
                return {
                    "ok": True,
                    "status_code": int(response.status_code),
                    "final_url": target.url,
                    "content_type": str(response.headers.get("content-type") or "").lower(),
                    "headers": dict(response.headers),
                    "body": body,
                    "text": text,
                    "hops": hops,
                    "peer_ip": peer_ip,
                    "tls_verified": target.url.startswith("https://"),
                }
        raise UnsafeTargetError("too_many_redirects", "Redirect limit exceeded.", url=current)
    finally:
        if owns_client:
            await client.aclose()
