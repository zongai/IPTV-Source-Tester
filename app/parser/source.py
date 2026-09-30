from pathlib import Path

import aiohttp

from app.parser.m3u import parse_m3u
from app.parser.stream_read import read_at_most


async def parse_playlist_source(source: str):
    if source.startswith(("http://", "https://")):
        timeout = aiohttp.ClientTimeout(total=120, connect=15, sock_connect=15, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(source, allow_redirects=True) as r:
                r.raise_for_status()
                # Loop-read: a single content.read(n) only returns one buffer.
                data = await read_at_most(r.content, 50 * 1024 * 1024)
                if len(data) > 50 * 1024 * 1024:
                    raise ValueError("remote playlist exceeds 50 MB")
                charset = r.charset or "utf-8"
                text = data.decode(charset, errors="replace")
                base = str(r.url)
        return parse_m3u(text, base_url=base)
    return parse_m3u(Path(source).read_text(encoding="utf-8", errors="replace"))
