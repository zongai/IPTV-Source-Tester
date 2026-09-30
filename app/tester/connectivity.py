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
    if isinstance(e, asyncio.TimeoutError):
        return 'TIMEOUT'
    if isinstance(e, aiohttp.ClientConnectorCertificateError):
        return 'TLS_ERROR'
    if isinstance(e, aiohttp.ClientConnectorError):
        m = str(e).lower()
        if 'refused' in m:
            return 'CONNECTION_REFUSED'
        if 'ssl' in m or 'certificate' in m:
            return 'TLS_ERROR'
        if 'name or service not known' in m or 'getaddrinfo' in m or 'nodename nor servname' in m:
            return 'DNS_ERROR'
        return 'CONNECTION_ERROR'
    if isinstance(e, aiohttp.ClientError):
        return 'NETWORK_ERROR'
    return 'NETWORK_ERROR'


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
        if p.scheme not in ('http', 'https') or not p.hostname:
            return ConnectivityResult(False, error_type='INVALID_RESPONSE', error_message='invalid URL')
        try:
            # aiohttp's connector has its own connection timeout, but DNS
            # resolution must also have an explicit bound; otherwise a stuck
            # resolver can hold a test slot indefinitely.
            timeout = session.timeout.connect or 10
            infos, dns = await _resolve(p.hostname, p.port or (443 if p.scheme == 'https' else 80), timeout)
            request_started = time.perf_counter()
            async with session.get(url, headers=headers, allow_redirects=True) as r:
                ttfb = time.perf_counter() - request_started
                await r.content.read(4096)
                if r.status >= 400:
                    return ConnectivityResult(False, r.status, r.headers.get('Content-Type'), dns, ttfb,
                                              f'HTTP_{r.status}', f'HTTP {r.status}', str(r.url))
                return ConnectivityResult(True, r.status, r.headers.get('Content-Type'), dns, ttfb,
                                          final_url=str(r.url))
        except Exception as e:
            return ConnectivityResult(False, error_type=classify_error(e), error_message=str(e)[:1000])
    return await run() if semaphore is None else await _guard(semaphore, run)


async def _guard(s, fn):
    async with s:
        return await fn()
