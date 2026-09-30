# 2026-09-30 — v0.5.0

## 导入与解析

- 修复大体积 M3U / HLS 清单被 aiohttp 单次 `read(n)` 截断的问题（新增 `stream_read.read_at_most`，循环读满）。
- EXTINF 解析正确处理引号内的逗号，避免频道名与属性被错误切断。
- 更完整识别 `EXTVLCOPT` / `EXTHTTP` 中的 User-Agent、Referer、Origin、Cookie、Authorization。
- 源身份键将 DB 中 `NULL` 与导入时缺失/空字符串视为相同，避免重复导入同一流。
- 启动时一次性去重历史重复源（保留最小 id，迁移测试结果，清理空频道）。
- 导入时跳过无 scheme/hostname 的非法 URL，以及元数据噪声条目。

## 测试器

- 连通性错误分类不再把 aiohttp 连接串里的 `ssl:default` 误判为 TLS 错误；优先识别拒绝连接与 DNS。
- FFprobe 调用与结果解析整理，headers 传递更稳健。
- HLS / 网络测试小幅加固。

## 导出与安全

- M3U 导出对属性与行内容做 CR/LF、引号清洗，降低注入风险。
- 系统状态接口对 `database_url` 做脱敏展示。

## 文档与 UI

- README / PORTAINER 明确：代码与界面挂载更新只需重启容器或刷新页面；仅运行环境（Dockerfile、requirements、FFmpeg 等）变更才需重建镜像。
- 前端页脚增加部署提示。
