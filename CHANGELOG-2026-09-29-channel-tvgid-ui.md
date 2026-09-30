# 2026-09-29 — tvg-id robustness + result explanation/colors

## Channel identification
- `tvg-id` is treated as metadata/EPG identity, not as the primary channel identity.
- Channel identity priority is: M3U display name (text after the comma) -> `tvg-name` -> `tvg-id` only when both names are absent.
- This prevents reused numeric IDs such as `1`, `2`, `3` from merging unrelated channels.
- Import stores `tvg-id` but does not use it to overwrite the channel name when a real display name exists.
- Existing URL deduplication remains authoritative: an existing URL is discarded before any channel mutation.

## Result UI
- Added a result legend for pass/fail/untested and score bands.
- Added numeric columns for resolution, score, speed, TTFB latency, and stability status.
- Added a numeric explanation of the 100-point score and its component thresholds.
- Scores: >=90 green, 70–89.99 amber, <70 red.
- Pass/fail/untested badges use green/red/gray respectively.

## API result selection
- Channel result display now prefers the latest validated result (`segment_valid IS NOT NULL`) so a later Quick connectivity check cannot hide the latest Standard/Full quality result.

## Validation
- Full pytest collection could not run in this environment because `apscheduler` is not installed.
- Relevant suite: 19 passed.
- `compileall`/syntax checks pass.
- Uploaded `10.m3u`: 488 parsed entries; after excluding the metadata entry `更新日期`, 45 distinct channel identities; `IPTV法治` occurs 9 times and is not over-assigned; `CCTV5` occurs 27 times in this file.
