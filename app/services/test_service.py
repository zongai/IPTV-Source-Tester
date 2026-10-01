import asyncio
import json
import socket
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

import aiohttp

from app.core.config import get_settings
from app.tester.connectivity import check_connectivity
from app.tester.ffprobe import run_ffprobe
from app.tester.hls import check_hls
from app.scoring.quality import calculate_score


class TestRunner:
    """Bounded-concurrency IPTV source tester.

    Origin-friendly defaults:
    - per-host semaphore (default 1 = serial queue per domain)
    - host cooldown after 403/429-like failures
    - mild default User-Agent when source has none
    - always forward source Referer/Origin/Cookie/Authorization
    - separate low FFprobe concurrency
    """

    def __init__(
        self,
        max_concurrency=None,
        max_host_concurrency=None,
        ffprobe_concurrency=None,
        connect_timeout=None,
        read_timeout=None,
        segment_test_count=None,
        host_cooldown_seconds=None,
    ):
        s = get_settings()
        self.max_concurrency = max_concurrency or s.max_concurrency
        self.global_sem = asyncio.Semaphore(self.max_concurrency)
        self.host_sems = {}
        self.host_limit = max(1, max_host_concurrency if max_host_concurrency is not None else s.max_host_concurrency)
        self.ffprobe_sem = asyncio.Semaphore(
            max(1, ffprobe_concurrency if ffprobe_concurrency is not None else s.ffprobe_concurrency)
        )
        self.connect_timeout = connect_timeout or s.connect_timeout
        self.read_timeout = read_timeout or s.read_timeout
        self.segment_test_count = segment_test_count or s.segment_test_count
        self.cooldown_seconds = (
            host_cooldown_seconds
            if host_cooldown_seconds is not None
            else s.host_cooldown_seconds
        )
        self.default_ua = s.default_user_agent
        self._host_cooldown_until: dict[str, float] = {}
        self._session = None

    def host_sem(self, host):
        key = (host or "").lower()
        return self.host_sems.setdefault(key, asyncio.Semaphore(self.host_limit))

    def _headers(self, source):
        """Prefer source headers; fall back to a mild fixed UA only for User-Agent."""
        ua = source.user_agent or self.default_ua
        return {
            k: v
            for k, v in {
                "User-Agent": ua,
                "Referer": source.referer,
                "Origin": source.origin,
                "Cookie": source.cookie,
                "Authorization": source.authorization,
            }.items()
            if v
        }

    async def _respect_host_cooldown(self, host: str):
        if self.cooldown_seconds <= 0:
            return
        key = (host or "").lower()
        until = self._host_cooldown_until.get(key)
        if not until:
            return
        delay = until - time.monotonic()
        if delay > 0:
            await asyncio.sleep(min(delay, float(self.cooldown_seconds)))

    def _note_host_failure(self, host: str, result: dict):
        """Cool down a host after rate-limit / hard reject signals."""
        if self.cooldown_seconds <= 0:
            return
        key = (host or "").lower()
        if not key:
            return
        status = result.get("http_status")
        err = (result.get("error_type") or "") + " " + (result.get("error_message") or "")
        err_u = err.upper()
        trip = status in (403, 429, 503) or any(
            x in err_u for x in ("429", "403", "RATE", "REFUSED", "TOO MANY")
        )
        if trip:
            self._host_cooldown_until[key] = time.monotonic() + float(self.cooldown_seconds)

    async def _ensure_session(self):
        if self._session is not None and not self._session.closed:
            return self._session
        timeout = aiohttp.ClientTimeout(
            total=self.read_timeout,
            connect=self.connect_timeout,
            sock_connect=self.connect_timeout,
            sock_read=self.read_timeout,
        )
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrency,
            limit_per_host=self.host_limit,
            ttl_dns_cache=300,
            family=socket.AF_UNSPEC,
        )
        self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def test_source(self, source, deep=True, mode=None):
        mode = mode or ("full" if deep else "standard")
        if mode not in {"quick", "standard", "full"}:
            mode = "full" if deep else "standard"

        session = await self._ensure_session()
        headers = self._headers(source)
        host = getattr(source, "host", "") or ""

        # Per-host first so one busy origin cannot hold all global slots.
        async with self.host_sem(host), self.global_sem:
            await self._respect_host_cooldown(host)
            c = await check_connectivity(source.url, session, headers)
            out = c.__dict__.copy()
            out["http_status"] = c.status
            out.pop("status", None)
            out["segment_valid"] = None if mode == "quick" else False
            out["playlist_valid"] = None if mode == "quick" else False
            if not c.ok:
                if mode != "quick":
                    out["error_type"] = c.error_type or "CONNECTION_ERROR"
                    out["error_message"] = c.error_message or "connection failed"
                self._note_host_failure(host, out)
                return out
            if mode == "quick":
                out["error_type"] = None
                out["error_message"] = None
                return out

            h = await check_hls(
                source.url,
                session,
                self.segment_test_count,
                headers,
            )
            hdict = h.__dict__.copy()
            h_valid = bool(h.valid)
            hdict["playlist_valid"] = h_valid
            hdict["segment_valid"] = h_valid
            hdict.pop("valid", None)
            if hdict.get("segment_details"):
                details = hdict.pop("segment_details")
                base_message = hdict.get("error_message") or ""
                hdict["error_message"] = (
                    base_message + " | segments=" + json.dumps(details, ensure_ascii=False)
                )[:4000]
            out.update(hdict)
            out["download_speed"] = h.avg_segment_speed_mbps
            out["min_speed"] = h.min_segment_speed_mbps
            out["max_speed"] = h.max_segment_speed_mbps
            out["startup_time"] = c.ttfb
            if h.valid:
                out["error_type"] = None
                out["error_message"] = None
                segment_availability = (
                    (h.segment_successes / h.segments_tested) if h.segments_tested else 0
                )
                out["stability"] = segment_availability
                out["failure_rate"] = 1 - segment_availability
                out["score"] = calculate_score(
                    segment_availability,
                    segment_availability,
                    (c.ttfb or 0) * 1000,
                    h.avg_segment_speed_mbps,
                    out.get("height"),
                )
            else:
                self._note_host_failure(host, out)
            if not h.valid or mode == "standard":
                return out

            # Full mode: FFprobe under a separate low concurrency limit.
            f = await run_ffprobe(source.url, headers, self.ffprobe_sem)
            out.update({k: v for k, v in f.__dict__.items() if k != "raw"})
            out["ffprobe_json"] = json.dumps(f.raw) if f.raw else None
            if not f.ok:
                out["segment_valid"] = False
                out["error_type"] = f.error_type or "FFPROBE_ERROR"
                out["error_message"] = f.error_message or "ffprobe failed"
                self._note_host_failure(host, out)
                return out
            out["score"] = calculate_score(
                segment_availability,
                segment_availability,
                (c.ttfb or 0) * 1000,
                h.avg_segment_speed_mbps,
                out.get("height"),
            )
            out["error_type"] = None
            out["error_message"] = None
            return out

    @staticmethod
    def _interleave_by_host(items):
        """Round-robin by host so one origin cannot monopolize the worker pool."""
        groups = defaultdict(deque)
        host_order = []
        for index, source in items:
            host = (getattr(source, "host", None) or "").lower()
            if host not in groups:
                host_order.append(host)
            groups[host].append((index, source))
        ordered = []
        active = deque(host_order)
        while active:
            host = active.popleft()
            item = groups[host].popleft()
            ordered.append(item)
            if groups[host]:
                active.append(host)
        return ordered

    async def test_many(self, sources, deep=True, mode=None, on_result=None):
        mode = mode or ("full" if deep else "standard")
        items = list(sources)
        results = [None] * len(items)
        queue = asyncio.Queue()
        for item in self._interleave_by_host(list(enumerate(items))):
            queue.put_nowait(item)

        async def worker():
            while True:
                try:
                    index, source = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    result = await self.test_source(source, deep=deep, mode=mode)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    result = exc
                results[index] = result
                try:
                    if on_result is not None:
                        value = on_result(index, source, result)
                        if asyncio.iscoroutine(value):
                            await value
                finally:
                    queue.task_done()

        n = min(self.max_concurrency, max(len(items), 1))
        workers = [asyncio.create_task(worker()) for _ in range(n)] if items else []
        try:
            if workers:
                await asyncio.gather(*workers)
            return results
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            await self.close()
