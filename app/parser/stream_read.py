"""Reliable body readers for aiohttp streams.

``StreamReader.read(n)`` returns *up to* n bytes from the current buffer; it does
not loop until n bytes are accumulated. Large M3U playlists and HLS manifests
were therefore silently truncated around one TCP buffer (~16 KiB).
"""

from __future__ import annotations


async def read_at_most(content, max_bytes: int, chunk_size: int = 64 * 1024) -> bytes:
    """Read until EOF or max_bytes+1 (so callers can detect oversize bodies)."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be >= 0")
    limit = max_bytes + 1
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        need = min(chunk_size, limit - total)
        chunk = await content.read(need)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)
