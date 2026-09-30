# IPTV Source Tester V4

Production-oriented IPTV source pool foundation implementing asynchronous connectivity/HLS/segment testing, bounded FFprobe, scoring, source pooling/failover selection, historical results, FastAPI/JSON/M3U APIs, WebSocket endpoint, CLI, SQLite/SQLAlchemy and Docker/FFmpeg packaging.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --reload
```

Set `API_TOKEN` for management endpoints. Set `PUBLIC_PLAYLIST=true` to expose player playlist endpoints. Never log Cookie/Authorization values.

## CLI

`iptv import playlist.m3u`

`iptv test --deep --channel cctv-1`

`iptv export --format m3u --output output.m3u`

`--duration` 当前只保留兼容参数，不会启动持续稳定性循环。

`iptv stats`

## Web 导入与测试结果订阅

打开 `http://<服务器>:8000/`（Portainer 示例端口为 `7777`）即可：

1. 上传 `.m3u` / `.m3u8` 文件；
2. 输入 HTTP/HTTPS M3U/M3U8 地址导入；
3. 查看导入数量和重复数量；
4. 点击“开始测试全部源”；
5. 查看每个源的通过状态、分辨率、评分、速度和错误类型；
6. 页面直接生成测试结果订阅地址。

订阅接口：

- `GET /api/subscription/m3u`：仅输出最近一次测试通过并达到默认评分 70 的源；
- `GET /api/subscription/json`：同样的结果，以 JSON 返回；
- `GET /api/playlists/m3u`：可自定义 `min_score`、`min_stability`、`min_height`、`min_speed`；
- `GET /api/playlists/json`：JSON 版本；
- `GET /api/player/channels`：播放器结构化频道接口。

示例：

```text
http://<服务器>:7777/api/subscription/m3u?min_score=70&min_height=720
```

当 `API_TOKEN` 为空时，上述接口无需 Token；设置 `API_TOKEN` 后则按 Bearer Token 鉴权。

## Web 定时任务

首页提供定时测试管理：

- 启用/停用自动测试
- 间隔 1~10080 分钟
- 快速/标准/完整（FFprobe）模式
- 所有启用源 / 仅失败源 / 超时未测试源
- 设置持久化到 SQLite，重启容器自动恢复
- Web 立即执行
- 显示上次执行、测试数量、失败数量、下次执行时间

API：

- `GET /api/scheduler`
- `PUT /api/scheduler`
- `POST /api/scheduler/run`

当 `API_TOKEN` 未设置或为空时，上述接口无需 Token；设置 Token 后使用 Bearer Token。

## 测试速度优化

测试器现在采用 asyncio 有界并发和共享 HTTP Session。Web 定时任务可以设置：

- 全局并发：默认 20
- 单 Host 并发：默认 5
- 连接超时：默认 5 秒
- 读取超时：默认 10 秒
- HLS 分片测试数量：默认 3

测试模式已经分级：

- Quick：仅 DNS/HTTP/响应检测，适合快速筛选
- Standard：HTTP + HLS + 分片
- Full：Standard + FFprobe

建议 Synology 从全局并发 20 开始，确认 CPU、网络和上游响应稳定后再逐步提高。

## 远程 M3U 定时获取

Web 管理界面支持维护多个远程 M3U/M3U8 订阅，每个订阅可单独设置获取间隔（1 分钟～7 天）。系统会在 APScheduler 中为每个远程订阅建立独立任务，定时下载并导入；重复 URL 不会重复创建 Source。

API：

- `GET /api/remote-playlists`
- `POST /api/remote-playlists`
- `PUT /api/remote-playlists/{id}`
- `DELETE /api/remote-playlists/{id}`
- `POST /api/remote-playlists/{id}/fetch`

导入阶段会忽略频道名称/tvg-id/tvg-name 为 `更新日期` 的条目。

## 本次修复说明（网络诊断 / 实时订阅 / M3U 频道归并）

- M3U/M3U8 导入自动清理 UTF-8 BOM，避免第一频道出现隐藏字符。
- 修正频道归并：未知中文/Unicode 频道不再全部归入 `unknown`，每个频道保持独立 ID。
- 重新导入相同 URL 时，如果历史数据库中的源属于错误频道，会自动修正频道归属；空频道自动清理。
- Standard（HLS+分片）测试在分片通过后立即计算评分、可用率和失败率，不需要等待 FFprobe。
- 订阅接口只读取最近一次已经完成 HLS/分片验证的结果，因此 Quick 测试不会覆盖已有合格结果；后续 Standard/Full 失败会正常使源退出订阅。
- M3U 订阅响应增加 `no-store`，避免浏览器/播放器缓存旧的空订阅。
- Web 测试过程中每 1.5 秒刷新测试结果和订阅统计，因此已有合格源会在测试尚未完成时立即出现在订阅中。
- `/api/network/check` 从 Tester 容器内部执行 DNS → TCP → TLS → HTTP 诊断，用于区分容器网络问题和 IPTV 源自身问题。


## 代码审查后的重要行为

- Standard 测试完成 HLS + 指定数量分片后即可产生评分和订阅结果，不需要等待 FFprobe。
- Full 模式只有 FFprobe 成功才保留最终通过状态。
- 网络诊断区分 `network_ok` 与 `http_ok`：HTTP 403/404 说明服务器可达但业务请求被拒绝，不再误判为 NAS/Docker 网络故障。
- HLS Segment 记录具体 HTTP/TLS/DNS/TIMEOUT/EMPTY/HTML 等错误，并限制 Playlist/Segment 内存读取上限。
- SQLite 写入统一串行化；手动测试停止会真正取消任务。
- 测试结果页面刷新后会尝试恢复当前进程中的活动任务轮询。
- TestResult 历史按 `HISTORY_RETENTION_DAYS` 在应用启动时清理。

## 当前仍需注意的限制

1. 活动测试任务状态目前保存在进程内存；容器重启后不会恢复正在执行的任务，只会保留已经提交到 SQLite 的历史结果。
2. `SourcePool`、持续 Stability 测试和自动连续失败删除尚未完全接入 Web 测试主流程；不能把现有 `source_pool.py` 视为已经启用的自动删除机制。
3. CLI 的 `--duration` 仍未实现真正的持续稳定性测试。
4. 公开订阅如果包含 Cookie/Authorization/Origin，会把这些播放所需 Header 一并输出；生产环境不要把带敏感 Header 的订阅设置为公开。

### 远程 M3U 失效自动删除

远程 M3U 自动获取具有失效保护：HTTP 400/401/403/404/410/422、空 M3U 或无效 M3U 内容会立即删除远程订阅配置；超时、连接失败、HTTP 5xx 等临时错误默认连续失败 3 次后删除。阈值可通过 `REMOTE_PLAYLIST_MAX_FAILURES` 配置。自动删除只移除远程订阅配置和对应定时任务，不删除已经导入的频道和源。
