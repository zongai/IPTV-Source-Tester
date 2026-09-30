# 2026-09-29 修正说明

## 测试并发
- Standard / Full 的连接失败现在直接记录 `segment_valid=false`、`playlist_valid=false`，不再显示为“未测试”。
- 每个源测试时先获取 host semaphore，再获取 global semaphore，避免同一 host 的等待任务占满全局并发槽。
- 测试队列按 host 轮询交错排列，避免同一 host 连续占据 worker 队列。

## 结果字段
- Standard / Full 成功结果显式清除 `error_type` / `error_message`，不再写入冗余错误信息。
- Full 的 FFprobe 成功同样清理错误字段；FFprobe 失败保留明确错误类型和消息。

## M3U 导入
- URL 是唯一导入身份：数据库中已经存在的 normalized URL 直接丢弃，不再因为新 M3U 的频道元数据而重绑已有 Source。
- 同一次 M3U 内重复 URL 也会被丢弃；由于项目 Session 使用 `autoflush=False`，导入服务现在维护内存 URL 集合确保这一点。

## 频道识别与排序
- `CCTV5` 与 `CCTV5+` 分别识别为 `cctv-5` 和 `cctv-5-plus`。
- 支持 `CCTV-5+`、`CCTV 5 Plus` 等等价写法。
- 输出频道按 CCTV 数字自然排序，例如 `CCTV1, CCTV2, CCTV5, CCTV5+, CCTV10`。
- 其它频道按规范化名称排序。

## 验证
- 定向测试：20 passed。
- `compileall` 通过。
- 完整 pytest 在当前离线环境无法收集 API 测试，因为环境缺少 APScheduler 且无法联网安装；项目 requirements.txt 已包含 `apscheduler>=3.10,<4`。其余测试已执行。
