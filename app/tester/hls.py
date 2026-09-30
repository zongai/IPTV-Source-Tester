import asyncio
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import aiohttp

from app.core.config import get_settings
from app.parser.m3u8 import parse_m3u8


@dataclass
class HLSResult:
    valid: bool
    playlist_type: str | None = None
    segments_tested: int = 0
    segment_successes: int = 0
    avg_segment_speed_mbps: float | None = None
    min_segment_speed_mbps: float | None = None
    max_segment_speed_mbps: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    segment_details: list[dict] = field(default_factory=list)
    playlist_url: str | None = None


def _classify_exc(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, aiohttp.ClientConnectorCertificateError):
        return "TLS_ERROR"
    if isinstance(exc, aiohttp.ClientConnectorError):
        text = str(exc).lower()
        if "refused" in text:
            return "CONNECTION_REFUSED"
        if "name or service not known" in text or "getaddrinfo" in text:
            return "DNS_ERROR"
        if "ssl" in text or "certificate" in text:
            return "TLS_ERROR"
        return "CONNECTION_ERROR"
    if isinstance(exc, aiohttp.ClientError):
        return "NETWORK_ERROR"
    return "NETWORK_ERROR"


def _playlist_type(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#EXT-X-PLAYLIST-TYPE:"):
            value = line.split(":", 1)[1].strip().upper()
            if value in {"VOD", "EVENT"}:
                return value
    return "VOD" if "#EXT-X-ENDLIST" in text else "LIVE"


def _variants(text: str, base_url: str) -> list[tuple[int, int, str]]:
    """Return (bandwidth, height, url), highest quality first."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    found = []
    for i, line in enumerate(lines[:-1]):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        next_line = lines[i + 1]
        if next_line.startswith("#"):
            continue
        attrs = dict(re.findall(r'([A-Z0-9-]+)=((?:"[^"]*")|[^,]+)', line.split(":", 1)[1]))
        def num(name):
            try:
                return int(str(attrs.get(name, "0")).strip('"'))
            except ValueError:
                return 0
        height = 0
        res = str(attrs.get("RESOLUTION", "")).strip('"')
        if "x" in res:
            try:
                height = int(res.split("x", 1)[1])
            except ValueError:
                pass
        found.append((num("BANDWIDTH"), height, urljoin(base_url, next_line)))
    return sorted(found, key=lambda x: (x[1], x[0]), reverse=True)


async def _read_playlist(url, session, headers):
    started = time.perf_counter()
    try:
        async with session.get(url, headers=headers, allow_redirects=True) as r:
            elapsed = time.perf_counter() - started
            status = r.status
            final_url = str(r.url)
            if status >= 400:
                return None, HLSResult(False, error_type=f"HTTP_{status}",
                                       error_message=f"playlist HTTP {status} ({elapsed:.2f}s)",
                                       playlist_url=final_url)
            max_bytes = int(get_settings().max_playlist_bytes)
            body = await r.content.read(max_bytes + 1)
            if len(body) > max_bytes:
                return None, HLSResult(False, error_type="PLAYLIST_TOO_LARGE",
                                       error_message=f"playlist exceeds {max_bytes} bytes",
                                       playlist_url=final_url)
            return (body.decode(r.charset or "utf-8", errors="replace"), final_url), None
    except Exception as exc:
        return None, HLSResult(False, error_type=_classify_exc(exc),
                               error_message=str(exc)[:1000], playlist_url=url)


async def _download_segment(segment_url, session, headers, max_bytes, retries):
    last = None
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            async with session.get(segment_url, headers=headers, allow_redirects=True) as r:
                if r.status >= 400:
                    err = {"status": r.status, "error_type": f"HTTP_{r.status}",
                           "error": f"segment HTTP {r.status}", "attempt": attempt + 1}
                    if r.status in {408, 429} or r.status >= 500 and attempt < retries:
                        last = err
                        await asyncio.sleep(min(2.0, 0.25 * (2 ** attempt)))
                        continue
                    return False, err
                total = 0
                first = b""
                async for chunk in r.content.iter_chunked(64 * 1024):
                    if not first:
                        first = chunk[:32]
                    total += len(chunk)
                    if total > max_bytes:
                        return False, {"status": r.status, "error_type": "SEGMENT_TOO_LARGE",
                                       "error": f"segment exceeds {max_bytes} bytes", "attempt": attempt + 1}
                elapsed = max(time.perf_counter() - started, 1e-6)
                if total == 0:
                    return False, {"status": r.status, "error_type": "EMPTY_SEGMENT",
                                   "error": "segment returned 0 bytes", "attempt": attempt + 1}
                content_type = (r.headers.get("Content-Type") or "").lower()
                if "text/html" in content_type or first.lstrip().startswith((b"<html", b"<!doctype")):
                    return False, {"status": r.status, "error_type": "INVALID_SEGMENT",
                                   "error": "segment returned HTML instead of media", "attempt": attempt + 1}
                speed = total * 8 / elapsed / 1e6
                return True, {"status": r.status, "ok": True, "bytes": total,
                              "elapsed": round(elapsed, 3), "speed_mbps": round(speed, 3),
                              "attempt": attempt + 1}
        except Exception as exc:
            err = {"error_type": _classify_exc(exc), "error": str(exc)[:300], "attempt": attempt + 1}
            last = err
            if err["error_type"] in {"TIMEOUT", "CONNECTION_ERROR", "CONNECTION_REFUSED", "NETWORK_ERROR"} and attempt < retries:
                await asyncio.sleep(min(2.0, 0.25 * (2 ** attempt)))
                continue
            return False, err
    return False, last or {"error_type": "SEGMENT_ERROR", "error": "unknown segment failure"}


async def check_hls(url, session, segment_count=3, headers=None):
    headers = headers or {}
    try:
        loaded, error = await _read_playlist(url, session, headers)
        if error:
            return error
        playlist_text, playlist_url = loaded
        p = parse_m3u8(playlist_text)
        if not p.is_valid:
            return HLSResult(False, error_type="INVALID_RESPONSE", error_message="invalid HLS playlist", playlist_url=playlist_url)

        variants = _variants(playlist_text, playlist_url)
        if variants:
            _, _, variant_url = variants[0]
            loaded_variant, variant_error = await _read_playlist(variant_url, session, headers)
            if variant_error:
                variant_error.error_type = variant_error.error_type or "VARIANT_ERROR"
                variant_error.error_message = f"variant playlist failed: {variant_error.error_message}"
                variant_error.playlist_url = variant_url
                return variant_error
            variant_text, variant_url_final = loaded_variant
            p = parse_m3u8(variant_text)
            playlist_url = variant_url_final
            playlist_text = variant_text
            if not p.is_valid:
                return HLSResult(False, error_type="INVALID_RESPONSE", error_message="invalid HLS variant playlist", playlist_url=variant_url)

        ptype = _playlist_type(playlist_text)
        if not p.segments:
            return HLSResult(False, ptype, error_type="INVALID_RESPONSE", error_message="playlist has no media segments", playlist_url=playlist_url)

        selected = p.segments[-max(1, segment_count):]
        settings = get_settings()
        max_bytes = int(settings.max_segment_bytes)
        retries = int(settings.network_retries)
        speeds = []
        details = []
        for seg in selected:
            segment_url = urljoin(playlist_url, seg)
            ok, item = await _download_segment(segment_url, session, headers, max_bytes, retries)
            item["url"] = segment_url
            details.append(item)
            if ok:
                speeds.append(item["speed_mbps"])

        successes = sum(1 for x in details if x.get("ok"))
        if not successes:
            first = details[0] if details else {}
            return HLSResult(False, ptype, len(selected), 0,
                             error_type=first.get("error_type", "SEGMENT_ERROR"),
                             error_message=f"all {len(selected)} segments failed; first={first.get('error', 'unknown')}",
                             segment_details=details, playlist_url=playlist_url)

        all_ok = successes == len(selected)
        return HLSResult(all_ok, ptype, len(selected), successes,
                         sum(speeds) / len(speeds), min(speeds), max(speeds),
                         error_type=None if all_ok else "PARTIAL_SEGMENT_FAILURE",
                         error_message=None if all_ok else f"{len(selected)-successes} of {len(selected)} segments failed",
                         segment_details=details, playlist_url=playlist_url)
    except Exception as exc:
        return HLSResult(False, error_type=_classify_exc(exc), error_message=str(exc)[:1000], playlist_url=url)
