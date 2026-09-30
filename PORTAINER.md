# IPTV Source Tester V4 — Portainer 部署

## 推荐方式：固定运行环境镜像 + Host 挂载代码

本项目将“运行环境”和“应用代码”分开：

- `iptv-source-tester:v4`：Python、FFmpeg、系统依赖，只在运行环境发生变化时重新构建；
- `/volume2/Data/iptv-tester/app`：Python 应用代码，直接挂载；
- `/volume2/Data/iptv-tester/frontend`：Web 前端，直接挂载；
- `/volume2/Data/iptv-tester/migrations`、`VERSION`：运行时资源，直接挂载；
- `/volume2/Data/iptv-tester/data`：SQLite 数据。

| 变更内容 | 需要做什么 |
|----------|------------|
| `app/`、`frontend/`、`migrations/`、`VERSION`、业务配置 | **不要**重建镜像；Python 代码改完**重启容器**，前端一般**刷新页面**即可 |
| `Dockerfile`、`requirements.txt`、Python 版本、FFmpeg、系统包 | **必须重新构建镜像**，再滚动更新/重建容器 |

> **默认提醒：只有运行环境变更才需要重新构建镜像。**  
> 日常发版与修 bug 属于代码挂载更新，重建镜像既慢也容易用到旧层缓存。

### 1. 先准备固定运行环境镜像

**首次部署**，或确认运行环境（依赖/基础镜像）已变化时：

```bash
cd /volume2/Data/iptv-tester
docker build -t iptv-source-tester:v4 .
```

如果只是修改 `app/`、`frontend/`、`migrations/` 或 `VERSION`，**不要重新 build**。

### 2. 创建 Stack

Portainer → **Stacks** → **Add stack** → Web editor。

使用本项目的 `docker-compose.portainer.yml`。Compose 已经使用固定镜像，并将宿主机项目目录挂载进容器。

### 3. 环境变量

在 Environment variables 中设置：

```text
TZ=Europe/Amsterdam
MAX_CONCURRENCY=100
MAX_HOST_CONCURRENCY=5
CONNECT_TIMEOUT=5
READ_TIMEOUT=10
FFPROBE_TIMEOUT=15
SEGMENT_TEST_COUNT=3
TEST_INTERVAL_MINUTES=30
MIN_SCORE=70
MIN_STABILITY=0.90
API_TOKEN=请替换成随机长Token
PUBLIC_PLAYLIST=false
HISTORY_RETENTION_DAYS=30
```

如果 API 不直接暴露到公网，`API_TOKEN` 仍建议设置。

### 4. 部署

点击 **Deploy the stack**。

容器：

```text
iptv-source-tester
```

Web/API：

```text
http://服务器IP:8000
```

健康检查：

```text
GET /health
```

## 数据持久化

Compose 自动创建 Docker named volume：

```text
iptv_tester_data
```

数据库位置：

```text
/data/iptv.db
```

删除/重新创建容器不会丢失数据库，只要不删除该 volume。

## Portainer Web Editor

如果你使用 Web Editor 而不是 Git Stack，`build: .` 必须能够访问完整项目目录；仅粘贴 Compose YAML 本身不足以构建这个项目。

没有 Git 仓库时，推荐先把本目录推送到 GitHub/GitLab/Gitea，再让 Portainer 从 Git 部署。

## API Token

如果设置：

```text
API_TOKEN=xxxxxxxx
```

需要在受保护 API 请求中发送：

```text
Authorization: Bearer xxxxxxxx
```

`/health` 不要求 Token。

## 播放列表

默认：

```text
PUBLIC_PLAYLIST=false
```

这样播放列表 API 仍受 API Token 保护。

如果明确需要让播放器无需认证读取播放列表，可设置：

```text
PUBLIC_PLAYLIST=true
```

## 自动检测

容器启动后 APScheduler 会按：

```text
TEST_INTERVAL_MINUTES
```

执行快速/完整源测试，并把结果写入 SQLite 历史记录。

默认 30 分钟。
