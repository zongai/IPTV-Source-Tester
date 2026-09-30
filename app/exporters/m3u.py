def _safe_attr(value) -> str:
    """Strip CR/LF and quotes to prevent M3U attribute / line injection."""
    text = str(value).replace("\r", " ").replace("\n", " ").replace('"', "'")
    return text.strip()


def _safe_line(value) -> str:
    return str(value).replace("\r", "").replace("\n", "").strip()


def render_m3u(entries):
    lines = ["#EXTM3U"]
    for e in entries:
        attrs = " ".join(
            f'{k}="{_safe_attr(v)}"'
            for k, v in e.get("attrs", {}).items()
            if v is not None
        )
        name = _safe_line(e.get("name", ""))
        lines.append(f"#EXTINF:-1 {attrs},{name}".rstrip())
        for k, v in e.get("headers", {}).items():
            if v is None:
                continue
            key = k.lower()
            val = _safe_line(v)
            if key == "user-agent":
                lines.append("#EXTVLCOPT:http-user-agent=" + val)
            elif key == "referer":
                lines.append("#EXTVLCOPT:http-referrer=" + val)
            elif key == "origin":
                lines.append("#EXTVLCOPT:http-origin=" + val)
            elif key == "cookie":
                lines.append("#EXTVLCOPT:http-cookie=" + val)
            elif key == "authorization":
                lines.append("#EXTVLCOPT:http-authorization=" + val)
        url = _safe_line(e.get("url", ""))
        if url:
            lines.append(url)
    return "\n".join(lines) + "\n"
