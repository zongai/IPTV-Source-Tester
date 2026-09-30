import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import get_settings


@dataclass
class FFProbeResult:
    ok: bool
    raw: dict | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: int | None = None
    error_type: str | None = None
    error_message: str | None = None


def _fps(v):
    try:
        a, b = v.split("/")
        return float(a) / float(b) if float(b) else None
    except Exception:
        return None


async def run_ffprobe(url, headers=None, semaphore=None):
    async def run():
        scheme = (urlsplit(url).scheme or "").lower()
        if scheme not in {"http", "https"}:
            return FFProbeResult(
                False,
                error_type="UNSUPPORTED_PROTOCOL",
                error_message=f"ffprobe skipped for non-http URL scheme: {scheme or 'none'}",
            )

        timeout = float(get_settings().ffprobe_timeout)
        # rw_timeout is microseconds for ffmpeg/ffprobe network IO.
        rw_us = max(1, int(timeout * 1_000_000))
        cmd = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            "-rw_timeout", str(rw_us),
            "-timeout", str(rw_us),
        ]
        if headers:
            cmd += [
                "-headers",
                "".join(f"{k}: {v}\r\n" for k, v in headers.items()),
            ]
        cmd.append(url)

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout + 2)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.communicate(), 3)
                except Exception:
                    pass
                return FFProbeResult(
                    False, error_type="TIMEOUT", error_message="ffprobe timeout"
                )
            if proc.returncode:
                return FFProbeResult(
                    False,
                    error_type="FFPROBE_ERROR",
                    error_message=err.decode(errors="replace")[-1000:],
                )
            raw = json.loads(out)
            streams = raw.get("streams", [])
            v = next((x for x in streams if x.get("codec_type") == "video"), {})
            a = next((x for x in streams if x.get("codec_type") == "audio"), {})
            br = v.get("bit_rate") or raw.get("format", {}).get("bit_rate")
            return FFProbeResult(
                True,
                raw,
                v.get("codec_name"),
                a.get("codec_name"),
                v.get("width"),
                v.get("height"),
                _fps(v.get("avg_frame_rate") or v.get("r_frame_rate")),
                int(br) if br and str(br).isdigit() else None,
            )
        except FileNotFoundError:
            return FFProbeResult(
                False,
                error_type="FFPROBE_UNAVAILABLE",
                error_message="ffprobe not installed",
            )
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.communicate(), 2)
                except Exception:
                    pass
            raise
        except Exception as e:
            return FFProbeResult(
                False, error_type="FFPROBE_ERROR", error_message=str(e)[:1000]
            )

    return await run() if semaphore is None else await _guard(semaphore, run)


async def _guard(s, f):
    async with s:
        return await f()
