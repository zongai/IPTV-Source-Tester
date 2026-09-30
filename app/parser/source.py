import aiohttp
from urllib.parse import urljoin
from pathlib import Path
from app.parser.m3u import parse_m3u


async def parse_playlist_source(source: str):
    if source.startswith(('http://', 'https://')):
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(source, allow_redirects=True) as r:
                r.raise_for_status()
                data = await r.content.read(50 * 1024 * 1024 + 1)
                if len(data) > 50 * 1024 * 1024:
                    raise ValueError('remote playlist exceeds 50 MB')
                text = data.decode(r.charset or 'utf-8', errors='replace')
                base = str(r.url)
        return parse_m3u(text, base_url=base)
    return parse_m3u(Path(source).read_text(encoding='utf-8', errors='replace'))
