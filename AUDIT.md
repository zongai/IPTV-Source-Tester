# IPTV Tester V4 代码审查报告

审查对象：`iptv-tester-realtime-subscription-fixed.zip`

## 本轮确认并修复

### P0/P1

1. **HTTP 状态字段丢失**
   - `ConnectivityResult.status` 没有映射到 `TestResultDB.http_status`。
   - 结果页/历史数据会出现 HTTP 状态为空。
   - 已修复。

2. **下载速度字段一直为空**
   - HLS 已计算 `avg/min/max_segment_speed_mbps`，但 `TestRunner` 没有写入 `download_speed/min_speed/max_speed`。
   - 已修复，Standard 测试即可保存速度和评分。

3. **Scheduler Quick 会错误把源标记为失败**
   - `segment_valid=None` 时使用了“字段存在”而不是“字段非 None”判断。
   - Quick 测试会把源错误改成 `temporarily_failed`。
   - 已修复。

4. **手动停止任务实际没有停止**
   - 原 `/tests/stop` 只修改状态，不取消 asyncio Task。
   - 已改为真正 `task.cancel()`，并确保 runner/session 清理。

5. **SQLite 写锁不统一**
   - 手动测试和 Scheduler 各自维护不同的 asyncio lock，仍可能互相竞争 SQLite writer。
   - 已统一为 `app.database.locks.db_write_lock`。

6. **10,000 源会一次性创建大量 asyncio Task**
   - 原 `gather(*(one(...) for ...))` 会产生与源数量相同的任务对象。
   - 已改成固定数量 worker + queue，worker 数量受 `max_concurrency` 限制。

7. **HLS Segment 错误信息过于粗糙**
   - 已改成保存每个 Segment 的 HTTP 状态、错误类型、尝试次数、耗时、字节数和速度。
   - 不再把所有错误统一成 `SEGMENT_ERROR`。

8. **Segment 一次性 `read()`，存在高并发内存风险**
   - 已改为流式读取，并增加 `MAX_SEGMENT_BYTES` 限制。
   - Playlist 同样增加 `MAX_PLAYLIST_BYTES` 限制。

9. **HLS Master Playlist 处理过于简单**
   - 原代码固定使用第一个 Variant。
   - 已按分辨率/带宽选择较高质量 Variant，再测试真实 media segments。

10. **HLS VOD/Event 识别不准确**
    - 原代码默认 LIVE。
    - 已根据 `EXT-X-PLAYLIST-TYPE` / `EXT-X-ENDLIST` 判断。

11. **HLS 部分 Segment 成功也可能被当作通过**
    - 已要求选中的 Segment 全部成功才进入 `valid=True`。

12. **Full 模式 FFprobe 失败仍可能保留 Standard 的通过状态**
    - 已修复：Full 模式 FFprobe 失败会产生最终失败结果。

13. **DNS 解析没有显式超时**
    - `getaddrinfo()` 可能长期占住测试并发槽。
    - 已增加超时保护。

14. **网络诊断把 HTTP 403/404 当成整体网络失败**
    - 现在区分 `network_ok` 和 `http_ok`。
    - 例如 HTTP 403 表示 TCP/TLS/HTTP 服务可达，但业务请求被拒绝，不应判定 NAS/Docker 网络断开。

15. **IPv6 首地址失败可能导致网络诊断误判**
    - 网络诊断现在会尝试多个解析地址，而不是只使用第一条地址。

16. **历史统计把 Quick 的 `segment_valid=None` 当作失败**
    - 已修复，Quick 不再污染可用率/失败率。

17. **统计平均评分使用全部历史记录**
    - 原 dashboard 的 average_score 会把旧测试全部混在一起。
    - 已改为每个 Source 的最新已验证结果。

18. **订阅接口 N+1 查询严重**
    - 原实现每个 Source 单独查询最近结果。
    - 已改为 SQL window function，一次查询获得每个 Source 的最新已验证结果。

19. **频道页面显示旧测试结果而不是当前 Quick 测试**
    - 已改为频道结果页面优先显示最新测试结果；订阅接口仍只使用最新已验证结果。

20. **URL normalize 会对整个 URL 做 `unquote()`**
    - 可能破坏 IPTV 签名 URL、`%2F`、query token 等语义。
    - 已改为不解码 query/path 中的百分号编码，只规范 scheme/host/默认端口/尾部 slash。

21. **远程 M3U 缺少大小限制**
    - 已限制远程导入最大 50 MB。

22. **远程/手动 M3U 的相对 URL 不支持**
    - 远程 M3U 现在以最终响应 URL 为 base 解析相对地址。

23. **订阅输出丢失 Origin/Cookie/Authorization**
    - 已把这些 Header 继续传到 M3U 输出。
    - 注意：公开订阅因此可能泄露敏感 Header，生产环境必须谨慎设置 `PUBLIC_PLAYLIST`。

24. **历史保留配置只定义没有执行**
    - `HISTORY_RETENTION_DAYS` 原来没有实际清理逻辑。
    - 已在应用启动时清理过期 TestResult。

25. **CLI 原来只是打印假结果**
    - 已补上真实 import/test/export/stats/channels/sources 基础实现。
    - `--duration` 仍未实现持续稳定性循环，因此不会伪装成已实现。

## 本轮实际测试

- `python -m compileall -q app tests`：通过
- pytest：**17 passed**
- HLS Segment 404 诊断测试：通过
- 本地 HTTP HLS Standard 测试：通过
- 本地测试确认：
  - `http_status=200`
  - `playlist_valid=True`
  - `segment_valid=True`
  - `download_speed/min_speed/max_speed` 有值
  - `score` 有值
- 用户提供的 M3U：
  - 116 entries
  - 106 个频道 ID
  - `unknown=0`

完整 API pytest 在当前审查环境缺少 APScheduler Python 包，因此使用与项目接口兼容的测试 stub 完成 API 测试；Docker `requirements.txt` 本身包含 `apscheduler>=3.10,<4`，所以这不是项目 requirements 缺失，而是当前审查运行环境没有联网安装依赖。

## 仍存在的非 P0 问题

1. 活动测试任务状态仍主要保存在进程内存。容器重启后不会恢复正在执行的任务；已经提交到 SQLite 的结果不会丢失。
2. `SourcePool`、持续 Stability 测试尚未完全接入 Web 主测试流水线。
3. 自动连续失败删除源功能目前没有完整接入；不能把现有 `source_pool.py` 当作已经启用的自动删除机制。
4. CLI `--duration` 仍是兼容参数，不是真正持续稳定性测试。
5. 项目大量使用 `datetime.utcnow()`，当前 Python/SQLAlchemy 环境会产生 deprecation warning；不影响当前运行，但应逐步迁移到 timezone-aware UTC datetime。
