# IPTV Source Tester V4

IPTV 源检测与订阅输出工具：导入 M3U/M3U8、异步连通性/HLS/分片/FFprobe 测试、百分制评分、定时任务、远程订阅自动拉取、合格源 M3U/JSON 订阅，以及 Web 管理界面。

当前版本见仓库根目录 `VERSION` 文件。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **导入** | 本地上传或 HTTP(S) 远程 M3U/M3U8；按 URL+请求头去重；启动时清理历史重复源 |
| **远程订阅** | 按间隔自动拉取并导入；永久失效立即删配置，临时错误连续失败后删配置 |
| **测试模式** | 快速（仅连接）/ 标准（HLS+分片）/ 完整（含 FFprobe） |
| **评分** | 可用性、稳定性、延迟、速度、分辨率、启动时间，满分 100 |
| **分辨率** | 仅 FFprobe 写入；Quick/Standard 不覆盖已有分辨率 |
| **源清理** | 连续验证失败 ≥ N 次 **且** 失败跨度 ≥ M 天时自动删除源（默认 5/5） |
| **订阅** | 仅输出最近一次验证通过且满足筛选条件的源；支持下载命名 |
| **Logo** | 无效 `tvg-logo` 自动映射到 [vircloud/TVLogo](https://github.com/vircloud/TVLogo) |
| **Web** | 统计、导入、远程订阅、手动/定时测试、结果表（分页/搜索）、网络诊断（默认折叠） |
| **CLI** | 导入、测试、导出、统计 |

---

## 快速开始（本地）

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开：`http://127.0.0.1:8000/`

- 管理接口：设置环境变量 `API_TOKEN` 后使用 `Authorization: Bearer <token>`
- 公开订阅：`PUBLIC_PLAYLIST=true` 时，订阅/播放列表接口可不带 Token
- **不要**在日志中输出 Cookie / Authorization 明文

### CLI

```bash
iptv import playlist.m3u
iptv test --deep --channel cctv-1
iptv export --format m3u --output output.m3u
iptv stats
```

说明：`--duration` 仅保留兼容，**不会**启动持续稳定性循环。

---

## Docker / Portainer 部署

推荐：**固定运行环境镜像 + 宿主机挂载代码**。详见 [`PORTAINER.md`](PORTAINER.md) 与 `docker-compose.portainer.yml`。

| 变更内容 | 操作 |
|----------|------|
| `app/`、`frontend/`、`migrations/`、`VERSION` | **不必**重建镜像；Python 改完**重启容器**，前端一般**刷新页面** |
| `Dockerfile`、`requirements.txt`、Python、FFmpeg、系统包 | **必须重新构建镜像** |

```bash
# 仅首次或运行环境变更时
cd /path/to/iptv-tester
docker build -t iptv-source-tester:v4 .
# 再在 Portainer 中用 docker-compose.portainer.yml 部署 Stack
```

默认映射示例：`http://<服务器>:7777/` → 容器 `8000`。

数据目录建议持久化到宿主机（compose 中 `/data` → SQLite）。

---

## Web 使用流程

1. **导入**：上传 `.m3u` / `.m3u8` / `.txt`，或填写远程 HTTP(S) 地址  
2. **远程自动获取**（可选）：添加订阅名称、URL、间隔分钟数  
3. **手动测试**：选择快速/标准/完整，开始测试全部源；进度条与结果表实时更新  
4. **定时测试**：启用、设间隔与范围（全部启用 / 仅失败 / 超时未测），可立即执行  
5. **订阅**：设置最低评分、最低分辨率，复制 M3U/JSON 地址，或「保存」下载（自动文件名）  
6. **网络诊断**（辅助工具，默认折叠）：容器内 DNS → TCP → TLS → HTTP  

### 订阅地址示例

```text
http://<服务器>:7777/api/subscription/m3u?min_score=70&min_height=720
http://<服务器>:7777/api/subscription/json?min_score=70&min_height=720
# 下载时加 download=1，会带 Content-Disposition 文件名，例如：
# iptv-s70-h720-20260930.m3u
```

订阅内容为：**最近一次已验证**（`segment_valid` 非空）且 **通过**、满足 `min_score` / `min_height` 等条件、源为启用且非失败状态的条目。测试进行中也可边测边订。

---

## 测试模式说明

| 模式 | 行为 | `segment_valid` |
|------|------|-----------------|
| **快速** | 仅 HTTP 连通性 | 保持未设置（不参与「已验证」订阅筛选） |
| **标准** | 连通 + HLS 列表 + 分片下载测速 | 通过/失败 |
| **完整** | 标准 + FFprobe（编码/分辨率等） | FFprobe 失败则记为失败 |

分辨率、编码等媒体字段：**仅 FFprobe 成功时更新**；之后的 Quick/Standard 结果会沿用上次 FFprobe 的分辨率，避免被清空。

### 评分（满分 100）

- 可用性 30 + 稳定性 25 + 延迟 15 + 速度 15 + 分辨率 10 + 启动时间 5  
- 延迟按 TTFB；速度按平均分片 Mbps；分辨率按高度档位给分  

页面「数值说明」有完整档位与颜色含义。

---

## 自动清理策略

### 源（Source）

同时满足时删除该源及其测试历史（频道下无源则删空频道）：

1. 连续 **Standard/Full** 验证失败次数 ≥ `SOURCE_AUTO_DELETE_FAILURES`（默认 **5**）  
2. 该失败跨度 ≥ `SOURCE_AUTO_DELETE_DAYS` 天（默认 **5**）  

一次成功会打断连续失败计数。Quick 不计入。

### 远程 M3U 配置

- HTTP 400/401/403/404/410/422、空列表、无效内容 → **立即删除**该远程配置  
- 超时、连接失败、5xx 等 → 连续失败 ≥ `REMOTE_PLAYLIST_MAX_FAILURES`（默认 **3**）后删除  
- **只删远程订阅配置与对应定时任务，不删已导入的频道和源**

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DATABASE_URL` | `sqlite:///./data/iptv.db` | 数据库；容器内常用 `sqlite:////data/iptv.db` |
| `MAX_CONCURRENCY` | `100` | 全局测试并发 |
| `MAX_HOST_CONCURRENCY` | `5` | 单 Host 并发 |
| `CONNECT_TIMEOUT` / `READ_TIMEOUT` | `5` / `10` | 连接/读超时（秒） |
| `FFPROBE_TIMEOUT` | `15` | FFprobe 超时（秒） |
| `SEGMENT_TEST_COUNT` | `3` | 标准/完整模式测速分片数 |
| `TEST_INTERVAL_MINUTES` | `30` | 默认定时间隔 |
| `MIN_SCORE` / `MIN_STABILITY` | `70` / `0.90` | 订阅默认门槛 |
| `API_TOKEN` | 空 | 管理接口鉴权；空则管理接口不校验 |
| `PUBLIC_PLAYLIST` | `false` | `true` 时订阅接口可不带 Token |
| `HISTORY_RETENTION_DAYS` | `30` | 测试历史保留天数（启动 + 每日清理） |
| `NETWORK_RETRIES` | `1` | 网络重试次数 |
| `MAX_PLAYLIST_BYTES` | `2097152` | HLS 播放列表读取上限 |
| `MAX_SEGMENT_BYTES` | `33554432` | 单分片读取上限 |
| `REMOTE_PLAYLIST_MAX_FAILURES` | `3` | 远程订阅临时失败删除阈值 |
| `SOURCE_AUTO_DELETE_FAILURES` | `5` | 源连续失败删除阈值 |
| `SOURCE_AUTO_DELETE_DAYS` | `5` | 源失败跨度天数阈值 |

完整示例见 `.env.example`。

---

## 主要 HTTP API

鉴权：管理类接口在设置了 `API_TOKEN` 时需要 `Authorization: Bearer <token>`。订阅类在 `PUBLIC_PLAYLIST=true` 或未设置 Token 时按配置开放。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/system/version` | 版本与代码 revision |
| GET | `/api/system/status` | 状态（数据库 URL 已脱敏） |
| GET | `/api/statistics` | 概览统计 |
| GET | `/api/channels` | 频道结果（分页 `limit`/`offset`，筛选 `q`/`status`） |
| POST | `/api/playlists/import` | JSON `{ "url": "https://..." }` |
| POST | `/api/playlists/import-file` | 上传文件 |
| GET | `/api/subscription/m3u` | 合格源 M3U；`download=1` 触发附件名 |
| GET | `/api/subscription/json` | 合格源 JSON |
| GET | `/api/playlists/m3u` / `json` | 同上，可带筛选参数 |
| GET | `/api/player/channels` | 播放器结构化数据 |
| POST | `/api/tests/start` | `mode=quick\|standard\|full`，可选 `source_ids` |
| POST | `/api/tests/stop` | `job_id=` |
| GET | `/api/tests/active` | 活动任务 |
| GET | `/api/scheduler` | 定时配置与状态 |
| PUT | `/api/scheduler` | 更新定时配置 |
| POST | `/api/scheduler/run` | 立即执行一轮 |
| GET | `/api/scheduler/runs` | 运行历史 |
| CRUD | `/api/remote-playlists` | 远程订阅；`POST .../fetch` 立即拉取 |
| GET | `/api/network/check` | `target=` 网络诊断 |
| WS | `/ws/tests` | 测试进度推送 |

---

## 项目结构（简要）

```text
app/
  api/           # FastAPI 路由
  core/          # 配置、调度、版本
  database/      # 模型、仓库、维护、去重
  exporters/     # M3U 导出、Logo 解析
  matcher/       # 频道 ID / 排序
  parser/        # M3U/M3U8、URL 归一化、可靠流式读取
  scoring/       # 百分制评分
  services/      # 导入、测试、远程订阅
  tester/        # 连通性、HLS、FFprobe、网络诊断
  cli.py         # 命令行
  main.py        # 应用入口与生命周期
frontend/        # 单页管理界面
tests/           # pytest
Dockerfile
docker-compose.portainer.yml
PORTAINER.md
```

---

## 设计要点与限制

**要点**

- 大 M3U / HLS 使用循环读取，避免单次 `read(n)` 截断  
- 导入按「归一化 URL + 请求头」去重（`None` 与空字符串等价）  
- CCTV-5 与 CCTV-5+ 分频道；`group-title` 含逗号、IPv6 URL、非法端口单条跳过  
- 停止测试后任务进入终态，不长期占活动列表；FFprobe 取消时杀进程并带网络超时  
- 频道列表单次窗口查询 + 前端分页，避免 N+1 与整表卡顿  

**限制**

1. 进行中的测试任务状态在进程内存中，**容器重启不会恢复进行中的任务**（已写入 SQLite 的结果仍在）  
2. CLI `--duration` 未实现真正的长时稳定性循环  
3. 若订阅含 Cookie/Authorization/Origin，导出时会写入播放所需 Header；开启公开订阅时请注意敏感 Header 可能被暴露  

---

## 开发与测试

```bash
pip install -r requirements.txt
pytest -q
```

贡献代码时请保持：不在日志中打印敏感 Header；新增环境变量同步 `.env.example` 与 compose。

---

## 许可证与致谢

- Logo 兜底数据来源：[vircloud/TVLogo](https://github.com/vircloud/TVLogo)（jsDelivr CDN）  
- 部署与问题排查优先阅读 [`PORTAINER.md`](PORTAINER.md)
