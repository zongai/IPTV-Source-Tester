# 2026-09-29 UI / Version / Portainer Mount Update

## Web result table
- Expanded result table container and added horizontal scrolling for narrow screens.
- Sticky table header, fixed column widths, zebra rows and hover state.
- Score, speed and latency are rendered as high-contrast status pills.
- Speed thresholds: green >= 10 Mbps, orange 2.5-<10 Mbps, red <2.5 Mbps.
- Latency thresholds: green <=250 ms, orange 250-1000 ms, red >1000 ms.
- Numeric explanation now matches the implemented score formula, including TTFB scoring.

## Versioning
- Added `VERSION` base version (`0.2.1`).
- Runtime version is `base_version + 8-character content revision`.
- The revision is a deterministic SHA-256 digest of `app/` and `frontend/` runtime files.
- Code/frontend changes therefore change the displayed version without rebuilding the image.
- Added public `/api/system/version` for the footer; protected system status remains protected.

## Portainer deployment
- `docker-compose.portainer.yml` no longer has `build:`.
- Runtime image is `iptv-source-tester:v4`.
- Host `app/`, `frontend/`, `migrations/`, and `VERSION` are bind-mounted.
- Host `/volume2/Data/iptv-tester/data` remains the persistent SQLite data directory.
- Rebuild the image only when the runtime environment changes (Python/OS/FFmpeg/dependencies).
