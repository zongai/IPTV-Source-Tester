# Remote M3U 自动失效删除

- 远程 M3U 返回 HTTP 400/401/403/404/410/422 时，视为配置/资源永久失效，立即删除远程订阅配置。
- HTTP 200 但 M3U 内容无效或没有播放条目时，立即删除远程订阅配置。
- 超时、连接失败、HTTP 5xx 等临时故障不会第一次就删除；默认连续失败 3 次后自动删除，可通过 `REMOTE_PLAYLIST_MAX_FAILURES` 调整（1-20）。
- 每次成功获取会将连续失败计数清零。
- 自动删除只删除 `remote_playlists` 配置记录及其定时任务，不删除已经导入的频道和 Source。
- Web 远程 M3U 列表显示连续失败次数；手动获取触发自动删除时会明确提示原因。
- SQLite 已增加兼容启动迁移，为已有数据库补充 `consecutive_failures` 与 `auto_deleted_at` 字段。
