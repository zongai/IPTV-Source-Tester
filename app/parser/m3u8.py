from dataclasses import dataclass, field

@dataclass
class HLSPlaylist:
    is_valid: bool
    playlist_type: str | None = None
    target_duration: float | None = None
    media_sequence: int | None = None
    segments: list[str] = field(default_factory=list)
    raw: str = ""

def parse_m3u8(text: str) -> HLSPlaylist:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines or lines[0] != "#EXTM3U":
        return HLSPlaylist(False, raw=text)
    target = sequence = None
    ptype = "LIVE"
    segments = []
    for line in lines[1:]:
        if line.startswith("#EXT-X-TARGETDURATION:"):
            try: target = float(line.split(":", 1)[1])
            except ValueError: pass
        elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try: sequence = int(line.split(":", 1)[1])
            except ValueError: pass
        elif line.startswith("#EXT-X-PLAYLIST-TYPE:"):
            ptype = line.split(":", 1)[1].strip().upper()
        elif not line.startswith("#"):
            segments.append(line)
    return HLSPlaylist(True, ptype, target, sequence, segments, text)
