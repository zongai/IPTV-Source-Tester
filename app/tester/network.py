import asyncio
import socket
import ssl
import time
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit

import aiohttp


@dataclass
class NetworkCheckResult:
    ok: bool
    target: str
    network_ok: bool = False
    dns_ok: bool = False
    dns_latency_ms: float | None = None
    tcp_ok: bool = False
    tcp_latency_ms: float | None = None
    tls_ok: bool | None = None
    tls_latency_ms: float | None = None
    http_ok: bool = False
    http_status: int | None = None
    http_latency_ms: float | None = None
    final_url: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self):
        return asdict(self)


def _error_type(exc):
    if isinstance(exc, asyncio.TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, aiohttp.ClientConnectorCertificateError) or isinstance(exc, ssl.SSLError):
        return "TLS_ERROR"
    if isinstance(exc, aiohttp.ClientConnectorError):
        msg = str(exc).lower()
        # Connector messages often embed "ssl:default"; check real causes first.
        if "refused" in msg:
            return "CONNECTION_REFUSED"
        if any(
            x in msg
            for x in (
                "getaddrinfo",
                "name or service not known",
                "nodename nor servname",
                "temporary failure in name resolution",
            )
        ):
            return "DNS_ERROR"
        if "certificate" in msg or "ssl handshake" in msg or "tlsv" in msg:
            return "TLS_ERROR"
        return "CONNECTION_ERROR"
    return "NETWORK_ERROR"


async def check_network(target: str, timeout: float = 8.0) -> NetworkCheckResult:
    p = urlsplit(target if "://" in target else f"https://{target}")
    if p.scheme not in ("http", "https") or not p.hostname:
        return NetworkCheckResult(False, target, error_type="INVALID_RESPONSE", error_message="invalid target URL")
    host = p.hostname
    port = p.port or (443 if p.scheme == "https" else 80)
    out = NetworkCheckResult(False, target)

    try:
        started = time.perf_counter()
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout
        )
        out.dns_ok = True
        out.dns_latency_ms = round((time.perf_counter() - started) * 1000, 2)
    except Exception as exc:
        out.error_type = _error_type(exc)
        out.error_message = f"DNS: {str(exc)[:500]}"
        return out

    # Try the resolved addresses until one connects. This avoids reporting a
    # false TCP failure just because an unreachable IPv6 address was returned first.
    connected_family = None
    for family, _, _, _, sockaddr in infos:
        try:
            started = time.perf_counter()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, family=family, ssl=None), timeout
            )
            out.tcp_ok = True
            out.tcp_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            connected_family = family
            writer.close()
            await writer.wait_closed()
            break
        except Exception as exc:
            out.error_type = _error_type(exc)
            out.error_message = f"TCP: {str(exc)[:500]}"
    if not out.tcp_ok:
        return out

    if p.scheme == "https":
        try:
            started = time.perf_counter()
            ctx = ssl.create_default_context()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ctx, server_hostname=host, family=connected_family), timeout
            )
            out.tls_ok = True
            out.tls_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            writer.close()
            await writer.wait_closed()
        except Exception as exc:
            out.tls_ok = False
            out.error_type = _error_type(exc)
            out.error_message = f"TLS: {str(exc)[:500]}"
            return out
    else:
        out.tls_ok = None

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=timeout, sock_connect=timeout, sock_read=timeout)
        started = time.perf_counter()
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(target, allow_redirects=True) as r:
                out.http_status = r.status
                out.http_latency_ms = round((time.perf_counter() - started) * 1000, 2)
                out.final_url = str(r.url)
                await r.content.read(1024)
                out.http_ok = r.status < 400
        # "ok" answers the network question, while http_ok answers the
        # application/HTTP question. A reachable server returning 403/404 is
        # not a NAS/Docker network failure.
        out.network_ok = bool(out.dns_ok and out.tcp_ok and out.tls_ok is not False)
        out.ok = out.network_ok
        if not out.http_ok:
            out.error_type = f"HTTP_{out.http_status}"
            out.error_message = f"HTTP status {out.http_status}"
        return out
    except Exception as exc:
        out.network_ok = bool(out.dns_ok and out.tcp_ok and out.tls_ok is not False)
        out.ok = False
        out.error_type = _error_type(exc)
        out.error_message = f"HTTP: {str(exc)[:500]}"
        return out
