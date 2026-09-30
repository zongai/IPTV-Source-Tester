import asyncio
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp


@dataclass
class ConnectivityResult:
    ok: bool
    status: int | None = None
    content_type: str | None = None
    dns_latency: float | None = None
    ttfb: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    final_url: str | None = None


def classify_error(e):
    """Classify network errors without mistaking connector ssl:default for TLS."""
    if isinstance(e, asyncio.TimeoutError):
        return "TIMEOUT"
    if isinstance(e, aiohttp.ClientConnectorCertificateError):
        return "TLS_ERROR"
    if isinstance(e, aiohttp.ClientConnectorError):
        m = str(e).lower()
        # Order matters: connector strings often embed "ssl:default" even when
        # the real failure is DNS or connection refused.
        if "refused" in m or "connect call failed" in m and "111" in m:
            return "CONNECTION_REFUSED"
        if any(
            x in m
            for x in (
                "name or service not known",
                "getaddrinfo",
                "nodename nor servname",
                "temporary failure in name resolution",
                "dns",
            )
        ):
            return "DNS_ERROR"
        if "certificate" in m or "ssl handshake" in m or "sslv3" in m or "tlsv" in m:
            return "TLS_ERROR"
        # Bare "ssl" is too broad (aiohttp includes ssl:default in many messages).
        return "CONNECTION_ERROR"
    if isinstance(e, aiohttp.ClientError):
        return "NETWORK_ERROR"
    return "NETWORK_ERROR"


async def _resolve(host, port, timeout):
    loop = asyncio.get_running_loop()
    started = time.perf_counter()
    infos = await asyncio.wait_for(
        loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=timeout
    )
    return infos, time.perf_counter() - started


async def check_connectivity(url, session, headers=None, semaphore=None):
    async def run():
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return ConnectivityResult(
                False, error_type="INVALID_RESPONSE", error_message="invalid URL"
            )
        try:
            timeout = session.timeout.connect or 10
            infos, dns = await _resolve(
                p.hostname, p.port or (443 if p.scheme == "https" else 80), timeout
            )
            request_started = time.perf_counter()
            async with session.get(url, headers=headers, allow_redirects=True) as r:
                ttfb = time.perf_counter() - request_started
                await r.content.read(4096)
                if r.status >= 400:
                    return ConnectivityResult(
                        False,
                        r.status,
                        r.headers.get("Content-Type"),
                        dns,
                        ttfb,
                        f"HTTP_{r.status}",
                        f"HTTP {r.status}",
                        str(r.url),
                    )
                return ConnectivityResult(
                    True,
                    r.status,
                    r.headers.get("Content-Type"),
                    dns,
                    ttfb,
                    final_url=str(r.url),
                )
        except Exception as e:
            return ConnectivityResult(
                False, error_type=classify_error(e), error_message=str(e)[:1000]
            )

    return await run() if semaphore is None else await _guard(semaphore, run)


async def _guard(s, fn):
    async with s:
        return await fn()
