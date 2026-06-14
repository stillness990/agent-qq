# agent-qq 安装部署手册

## 目录

- [1. 系统架构概述](#1-系统架构概述)
- [2. 环境要求](#2-环境要求)
- [3. 快速部署（一键脚本）](#3-快速部署一键脚本)
- [4. 手动部署](#4-手动部署)
- [5. Docker 部署](#5-docker-部署)
- [6. NapCat QQ 配置](#6-napcat-qq-配置)
- [7. Claude Code CLI 配置](#7-claude-code-cli-配置)
- [8. 配置参考](#8-配置参考)
- [9. Worker 池与任务调度](#9-worker-池与任务调度)
- [10. 通知系统配置](#10-通知系统配置)
- [11. systemd 服务配置](#11-systemd-服务配置)
- [12. 验证与测试](#12-验证与测试)
- [13. 日志与监控](#13-日志与监控)
- [14. 数据文件说明](#14-数据文件说明)
- [15. 常见问题](#15-常见问题)

---

## 1. 系统架构概述

```
┌──────────┐     ┌──────────────┐     ┌───────────────────────────────┐     ┌──────────────┐
│ QQ 客户端 │ ──→ │  NapCat QQ   │ ──→ │  agent-qq (bot.py)            │ ──→ │ Claude Code  │
│ (私聊消息) │ ←── │ (OneBot v11) │ ←── │  主进程 + WorkerPool 子进程   │ ←── │    CLI       │
└──────────┘     └──────────────┘     └───────────────────────────────┘     └──────────────┘
                      :3001                     :3001                          claude CLI
```

**进程架构：**

```
bot.py (主进程, asyncio)
  ├── OneBot 事件循环          → 接收 QQ 消息
  ├── command_router.py        → 命令解析与路由
  ├── task_monitor.py          → 后台健康检查 (5s)
  ├── task_registry.py         → 内存任务注册表
  ├── circuit_breaker.py       → 熔断保护
  ├── task_scheduler.py        → 调度 pending 任务 (daemon 线程)
  ├── task_cleaner.py          → 清理过期任务 (daemon 线程)
  └── task_recovery.py         → 启动时修复孤儿任务

bot.py (WorkerPool 子进程, multiprocessing)
  ├── Worker 1  ──→  Claude CLI  subprocess
  ├── Worker 2  ──→  Claude CLI  subprocess
  ├── Worker 3  ──→  Claude CLI  subprocess
  └── Worker 4  ──→  Claude CLI  subprocess
```

> **注意**：启动后看到 2 个 `bot.py` 进程是正常现象 — 1 个主进程 + 1 个 WorkerPool 子进程。

**核心组件：**

| 组件 | 文件 | 职责 |
|------|------|------|
| 主进程 | `bot.py` | 事件循环、组件编排 |
| QQ 客户端 | `qq_client.py` | OneBot v11 WebSocket 通信 |
| 命令路由 | `command_router.py` | 命令解析、消息去重 |
| Claude 客户端 | `claude_client.py` | Claude Code CLI 调用封装 |
| 计划状态机 | `plan_state.py` | /plan 生命周期管理 |
| 熔断保护 | `circuit_breaker.py` | Token/网络/超时异常检测 |
| 任务注册 | `task_registry.py` | 内存任务生命周期追踪 |
| 任务监控 | `task_monitor.py` | 后台健康检查（纯脚本） |
| 状态日志 | `task_status_log.py` | 持久化任务状态 |
| 原子存储 | `storage_manager.py` | filelock + 原子写入 JSON |
| Worker 池 | `worker_pool.py` | 多进程并行执行 Claude CLI |
| 任务调度 | `task_scheduler.py` | pending → idle worker 分配 |
| 启动恢复 | `task_recovery.py` | 修复孤儿任务和 Worker |
| 任务清理 | `task_cleaner.py` | 定期清理过期任务 |
| 通知系统 | `notifications/` | QQ 消息通知（Hook 驱动） |

---

## 2. 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | 运行 bot.py |
| NapCat QQ | 最新版 | QQ 机器人框架 |
| QQ | 任意版本 | 需要登录机器人账号 |
| Claude Code CLI | 最新版 | `npm install -g @anthropic-ai/claude-code` |
| Node.js | 18+ | Claude Code CLI 运行时 |
| git | 2.0+ | 可选，用于版本管理 |
| Docker | 24+ | 可选，用于容器化部署 |

**操作系统支持：** Linux（推荐 Ubuntu 22.04+）、macOS、Windows (WSL2)

---

## 3. 快速部署（一键脚本）

### 3.1 克隆项目

```bash
git clone https://github.com/stillness990/agent-qq.git
cd agent-qq
```

### 3.2 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 配置环境变量

```bash
# 创建 .env 文件（参考下方配置参考章节）
cat > .env << 'EOF'
ONEBOT_WS_URL=ws://127.0.0.1:3001
ADMIN_QQ_IDS=你的QQ号
ENABLE_PRIVATE_CHAT=true
CLAUDE_CLI_COMMAND=claude
CLAUDE_CONFIG_DIR=<PROJECT_PATH>
CLAUDE_WORKDIR=<PROJECT_PATH>
NAPCAT_QQ_ID=机器人QQ号
EOF
```

### 3.4 一键启动

```bash
./start.sh              # 启动
./start.sh --restart    # 重启
./start.sh --stop       # 停止
./start.sh --status     # 查看状态
```

脚本会自动完成：
1. 检测 Python 环境
2. 检测 NapCat/QQ 是否运行
3. 等待 OneBot WebSocket 端口就绪（最长 180 秒）
4. 检查是否有已有 bot.py 实例（防止双开）
5. 启动 bot.py 并验证运行状态

---

## 4. 手动部署

### 4.1 安装 Python 依赖

```bash
cd agent-qq
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

依赖清单（`requirements.txt`）：

```
aiohttp==3.12.13        # WebSocket 客户端
pydantic==2.11.7        # 配置模型
pydantic-settings==2.10.1  # .env 配置加载
python-dotenv==1.1.1    # 环境变量
pytest==8.4.1           # 测试框架（开发）
pytest-asyncio==1.0.0   # 异步测试（开发）
```

### 4.2 配置 .env 文件

最小可运行配置：

```env
# ── OneBot 连接 ──
ONEBOT_WS_URL=ws://127.0.0.1:3001
ONEBOT_ACCESS_TOKEN=

# ── QQ 配置 ──
NAPCAT_QQ_ID=机器人QQ号
ADMIN_QQ_IDS=你的管理员QQ号
ENABLE_PRIVATE_CHAT=true

# ── Claude Code CLI ──
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=./workspace
CLAUDE_CONFIG_DIR=<PROJECT_PATH>

# ── 日志 ──
LOG_LEVEL=INFO
```

### 4.3 启动 bot.py

```bash
# 前台运行（调试用）
.venv/bin/python bot.py

# 后台运行
nohup .venv/bin/python bot.py > logs/agent-qq.log 2>&1 &

# 或使用完整启动脚本
bash scripts/start_agent_qq.sh --foreground
```

`start_agent_qq.sh` 额外处理：
- 自动启动 NapCat QQ（如未运行）
- 等待 WebUI 端口（6099）和 OneBot 端口（3001）
- 发送上线通知（可配置）
- 支持 `--foreground` 和 `background` 两种模式

---

## 5. Docker 部署

### 5.1 构建与启动

```bash
cd agent-qq
docker compose up -d --build
```

### 5.2 docker-compose.yml 说明

```yaml
services:
  agent-qq:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: agent-qq
    restart: unless-stopped        # 异常退出自动重启
    env_file:
      - .env                        # 从 .env 加载全部配置
    volumes:
      - ./logs:/app/logs            # 日志持久化
      - ./plugins:/app/plugins      # 插件目录
      - ./agents:/app/agents        # Agent 目录
      - ${CLAUDE_CONFIG_DIR}:/root/.claude:ro  # Claude 配置（只读）
    extra_hosts:
      - "host.docker.internal:host-gateway"  # 访问宿主机服务
```

### 5.3 Docker 专用配置

容器内访问宿主机 NapCat 时，`.env` 中配置：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

### 5.4 Dockerfile 说明

```dockerfile
FROM python:3.12-slim
# 安装 Claude Code CLI（通过 npm）
RUN npm install -g @anthropic-ai/claude-code
# 安装 Python 依赖
COPY requirements.txt .
RUN pip install -r requirements.txt
# 复制项目文件
COPY . /app
CMD ["python", "bot.py"]
```

### 5.5 Docker 常用操作

```bash
# 查看日志
docker compose logs -f agent-qq

# 重启
docker compose restart agent-qq

# 停止
docker compose down

# 重新构建
docker compose build --no-cache agent-qq
docker compose up -d
```

---

## 6. NapCat QQ 配置

### 6.1 安装 NapCat QQ

```bash
# 方式一：一键安装脚本
curl -fsSL https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh | bash

# 方式二：使用 napcat-qq 命令行
napcat-qq -q 机器人QQ号
```

### 6.2 登录 QQ

首次启动 NapCat 后，访问 WebUI：

```
http://127.0.0.1:6099/webui
```

在 WebUI 中完成 QQ 扫码登录。

### 6.3 配置 OneBot v11 WebSocket

在 NapCat WebUI 中：

1. 进入「网络设置」或「OneBot 设置」
2. 添加 WebSocket Server：
   - **协议**: WebSocket (正向)
   - **监听地址**: `0.0.0.0`（或 `127.0.0.1` 仅本地访问）
   - **监听端口**: `3001`
   - **Access Token**: 可选（与 `.env` 中 `ONEBOT_ACCESS_TOKEN` 一致）
3. 保存配置，NapCat 会自动应用

### 6.4 验证 OneBot 连接

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001
```

成功输出示例：
```
Connected to OneBot: ws://127.0.0.1:3001
OK
```

---

## 7. Claude Code CLI 配置

### 7.1 安装

```bash
npm install -g @anthropic-ai/claude-code
```

### 7.2 登录与验证

```bash
# 登录 Anthropic 账号
claude login

# 验证
claude --version
claude -p "你好，请回复'OK'"
```

### 7.3 配置目录

Claude Code 的配置目录通常在 `~/.claude/`：

```
~/.claude/
├── settings.json      # 模型选择、权限等
├── credentials.json   # API 凭证（自动生成）
└── ...
```

Docker 部署时，将此目录挂载为只读：

```yaml
volumes:
  - ${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

---

## 8. 配置参考

### 完整 .env 配置项

```env
# ── OneBot 连接 ──
ONEBOT_WS_URL=ws://127.0.0.1:3001        # OneBot WebSocket 地址
ONEBOT_ACCESS_TOKEN=                      # Access Token（可选）

# ── QQ 配置 ──
NAPCAT_QQ_ID=<QQ_ID>                   # 机器人 QQ 号
ADMIN_QQ_IDS=<QQ_ID>                    # 管理员 QQ 号（多个用逗号分隔）
ENABLE_PRIVATE_CHAT=true                  # 是否启用私聊
QQ_REPLY_CHUNK_SIZE=1800                  # 回复消息分块大小（字符）

# ── Claude Code CLI ──
CLAUDE_CLI_COMMAND=claude                 # Claude CLI 命令
CLAUDE_TIMEOUT_SECONDS=180                # 单次调用超时（秒）
CLAUDE_WORKDIR=./workspace                # 工作目录
CLAUDE_CONFIG_DIR=~/.claude               # Claude 配置目录

# ── Shell 命令（管理员） ──
ENABLE_SHELL_COMMAND=false                # 是否启用 /shell
SHELL_ALLOWED_PREFIXES=pwd,ls,cat,grep    # 允许的命令前缀（逗号分隔）

# ── 日志 ──
LOG_LEVEL=INFO                            # DEBUG | INFO | WARNING | ERROR

# ── 重连 ──
RECONNECT_INITIAL_SECONDS=2               # 初始重连间隔（秒）
RECONNECT_MAX_SECONDS=60                  # 最大重连间隔（秒）

# ── 消息去重 ──
MESSAGE_DEDUPE_TTL_SECONDS=300            # 去重窗口（秒）

# ── 计划管理 ──
PLAN_HISTORY_MAX=50                       # 计划历史最大条数
PLAN_DATA_DIR=data                        # 计划数据目录
PLAN_STATUS_LOG_MAX_AGE_HOURS=24          # 状态日志保留时间（小时）

# ── 熔断保护 ──
CIRCUIT_BREAKER_ENABLED=true              # 是否启用熔断
CIRCUIT_BREAKER_MAX_RETRIES=3             # 最大重试次数
CIRCUIT_BREAKER_TASK_TIMEOUT_MINUTES=30   # 任务超时（分钟）

# ── 后台监控 ──
MONITOR_ENABLED=true                      # 是否启用后台监控
MONITOR_POLL_INTERVAL_SECONDS=5           # 监控轮询间隔（秒）

# ── Worker 池 ──
WORKER_POOL_ENABLED=true                  # 是否启用 Worker 池
WORKER_POOL_SIZE=4                        # Worker 数量（1-7）
TASK_MAX_AGE_HOURS=24                     # 任务保留时间（小时）

# ── 天气推送 ──
WEATHER_PUSH_SCRIPT=/path/to/weather.py   # 天气推送脚本路径
```

---

## 9. Worker 池与任务调度

### 9.1 概述

agent-qq v2 内置多进程 Worker 池，实现并行任务执行：

- **WorkerPool** — 独立子进程，管理 4 个并行 Worker（默认 `WORKER_POOL_SIZE=4`）
- **TaskScheduler** — daemon 线程，每秒轮询 pending 任务并分配给空闲 Worker
- **TaskCleaner** — daemon 线程，每 5 分钟清理超过 24 小时的已完成/已取消任务
- **TaskRecovery** — 启动时同步执行，修复孤儿任务和 Worker 状态

### 9.2 数据流

```
QQ 消息 → command_router → task_registry.create(task)
                                   ↓
                          task_status_log.json
                                   ↓
                 TaskScheduler (扫描 pending/running)
                      ├→ 找到 idle worker
                      └→ 分配: task.worker=W1, worker.status=busy
                                   ↓
                 WorkerPool (检测到 busy worker)
                      └→ 启动 Claude CLI subprocess
                                   ↓
                 Claude CLI 完成/失败
                      └→ 更新 task 状态, 释放 worker → idle
```

### 9.3 Worker 配置

```env
# ── Worker 池 ──
WORKER_POOL_ENABLED=true          # 是否启用 Worker 池
WORKER_POOL_SIZE=4                # Worker 数量（1-7）
TASK_MAX_AGE_HOURS=24             # 已完成任务保留时间（小时）
```

### 9.4 Worker 状态

查看 Worker 实时状态：

```bash
cat data/worker_state.json
```

示例输出：

```json
{
  "W1": {"status": "busy", "task": "t3"},
  "W2": {"status": "idle", "task": null},
  "W3": {"status": "idle", "task": null},
  "W4": {"status": "idle", "task": null}
}
```

### 9.5 任务队列

```bash
cat data/task_queue.json
```

任务状态说明：

| 状态 | 说明 |
|------|------|
| `pending` | 等待调度 |
| `running` | 已被 Worker 执行中 |
| `completed` | 执行成功 |
| `exception` | 执行失败 |
| `cancelled` | 已被用户取消 |

---

## 10. 通知系统配置

agent-qq 内置 Claude Code Hook 通知系统，在 Claude Code 任务执行过程中自动向 QQ 推送状态通知。

### 9.1 通知配置

```env
# ── 通知开关 ──
CLAUDE_NOTIFY_ENABLED=true                     # 是否启用通知

# ── 通知目标 ──
CLAUDE_NOTIFY_QQ_IDS=                          # 通知目标 QQ（逗号分隔，为空则发给管理员）
CLAUDE_NOTIFY_PREFIX=【Claude】                 # 消息前缀

# ── 消息格式 ──
CLAUDE_NOTIFY_MESSAGE_MAX_LEN=180              # 单条消息最大长度

# ── 频率控制 ──
CLAUDE_NOTIFY_STAGE_COOLDOWN_SECONDS=60        # 阶段通知冷却（秒）
CLAUDE_NOTIFY_FAILURE_COOLDOWN_SECONDS=180     # 失败通知冷却（秒）
CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS=8           # 最小发送间隔（秒）
CLAUDE_NOTIFY_MAX_PER_10_MINUTES=20            # 每10分钟最大条数
CLAUDE_NOTIFY_MAX_PER_HOUR=60                  # 每小时最大条数
CLAUDE_NOTIFY_SESSION_BUDGET=25                # 单次会话通知预算

# ── 通知类型控制 ──
CLAUDE_NOTIFY_SUCCESS_MODE=important           # off | important | all

# ── 心跳与长任务 ──
CLAUDE_NOTIFY_LONG_TASK_SECONDS=600            # 长任务阈值（秒）
CLAUDE_NOTIFY_HEARTBEAT_SECONDS=300            # 心跳间隔（秒）

# ── 状态持久化 ──
CLAUDE_NOTIFY_STATE_DIR=data/notify-state      # 通知状态存储目录
CLAUDE_NOTIFY_STATE_TTL_SECONDS=86400          # 状态过期时间（秒）

# ── 去重 ──
CLAUDE_NOTIFY_START_DEDUPE_SECONDS=30          # 启动去重窗口（秒）
CLAUDE_NOTIFY_STOP_DEDUPE_SECONDS=30           # 停止去重窗口（秒）

# ── 监控 ──
CLAUDE_NOTIFY_MONITOR_INTERVAL_SECONDS=30      # 监控轮询间隔（秒）
CLAUDE_NOTIFY_MONITOR_LOCK_TTL_SECONDS=120     # 监控锁 TTL（秒）

# ── 安全 ──
CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES=            # 允许通知的工作目录前缀
```

### 9.2 通知 Hook 注册

在 `~/.claude/settings.json` 中注册 Hook：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "command": "python /path/to/agent-qq/scripts/claude_notify_hook.py stage"
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "command": "python /path/to/agent-qq/scripts/claude_notify_hook.py stage"
      }
    ]
  }
}
```

### 9.3 手动发送通知

```bash
.venv/bin/python scripts/claude_notify_hook.py send "测试通知消息"
```

---

## 11. systemd 服务配置

### 10.1 创建服务文件

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/agent-qq.service << 'EOF'
[Unit]
Description=agent-qq QQ AI Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/agent-qq
ExecStart=%h/agent-qq/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10
StandardOutput=append:%h/agent-qq/logs/agent-qq.log
StandardError=append:%h/agent-qq/logs/agent-qq.log

[Install]
WantedBy=default.target
EOF
```

### 10.2 启用服务

```bash
systemctl --user daemon-reload
systemctl --user enable agent-qq.service
systemctl --user start agent-qq.service

# 查看状态
systemctl --user status agent-qq.service

# 查看日志
journalctl --user -u agent-qq.service -f
```

### 10.3 允许用户服务开机自启

```bash
sudo loginctl enable-linger $USER
```

---

## 12. 验证与测试

### 11.1 验证 OneBot 连接

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001
```

### 11.2 发送测试私聊

```bash
.venv/bin/python scripts/send_test_private_msg.py \
  --to 你的QQ号 \
  --message "agent-qq 测试消息"
```

如果 NapCat 配置了 Access Token：

```bash
.venv/bin/python scripts/send_test_private_msg.py \
  --to 你的QQ号 \
  --token 你的AccessToken \
  --message "agent-qq 测试消息"
```

### 11.3 QQ 内测试命令

向机器人发送以下私聊消息验证功能：

```
/help           # 查看命令列表
/ping           # 心跳检测
/status         # 运行状态
/network        # 网络测试
/plan 你好      # 测试 AI 交互（需 Claude Code CLI 就绪）
```

### 11.4 运行单元测试

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -v tests/test_command_router.py
```

---

## 13. 日志与监控

### 13.1 日志文件

| 文件 | 内容 |
|------|------|
| `logs/agent-qq.log` | 主日志（轮转，保留 5 个文件，每个 5MB） |
| `logs/napcat.log` | NapCat 启动日志 |
| `logs/bot_output.log` | 手动启动的 stdout/stderr |
| `data/pending_plan.json` | 当前待确认计划 |
| `data/plan_history.json` | 计划历史（最多 50 条） |
| `data/task_status_log.json` | 任务状态日志（完成/取消的任务 24 小时后自动清理） |
| `data/task_queue.json` | 任务队列（Worker 调度用） |
| `data/worker_state.json` | Worker 实时状态（idle/busy） |

### 13.2 查看运行状态

```bash
# 一键状态
./start.sh --status

# 手动
ps aux | grep bot.py
tail -f logs/agent-qq.log

# Worker 状态
cat data/worker_state.json
cat data/task_queue.json
```

### 13.3 网络测试

```bash
.venv/bin/python -c "from task_monitor import TaskMonitor; g,l,loss=TaskMonitor.check_network(); print(f'{g} 延迟:{l:.0f}ms 丢包:{loss:.0f}%')"
```

---

## 14. 数据文件说明

agent-qq 运行时在 `data/` 目录下生成以下文件：

| 文件 | 格式 | 用途 | 清理策略 |
|------|------|------|----------|
| `plan_history.json` | JSON 数组 | /plan 历史记录 | 最多保留 50 条 |
| `pending_plan.json` | JSON 对象 | 当前待确认计划 | 确认/取消时删除 |
| `task_status_log.json` | JSON 数组 | 任务状态持久化 | 24h 后清理 terminal 状态 |
| `task_queue.json` | JSON 数组 | Worker 调度任务队列 | TaskCleaner 定期清理 |
| `worker_state.json` | JSON 对象 | Worker 实时状态 | 不自动清理 |
| `notify-state/` | 目录 | 通知系统状态 | TTL 24h |

所有 JSON 文件通过 `storage_manager.py` 的 filelock + 原子写入机制保证跨进程安全。

---

## 15. 常见问题

### Q: 为什么有 2 个 bot.py 进程？

这是正常的。v2 架构使用 `multiprocessing.Process` 创建独立的 WorkerPool 子进程：
- 主进程：事件循环 + QQ 处理 + 调度器 + 清理器
- 子进程：WorkerPool（并行 Worker 执行 Claude CLI）

### Q: bot.py 启动后立即退出

检查日志：

```bash
tail -20 logs/agent-qq.log
```

常见原因：
- `ONEBOT_WS_URL` 不可达 → 确认 NapCat 已启动且 OneBot WebSocket 已启用
- Python 依赖缺失 → `pip install -r requirements.txt`
- `.env` 格式错误 → 检查配置值是否合法

### Q: 收到两条相同回复

原因：有多个 `bot.py` 进程在运行。解决：

```bash
./start.sh --restart   # 自动清理旧进程并重启
```

### Q: /plan 命令无响应

检查 Claude Code CLI 是否可用：

```bash
claude --version
claude -p "测试"
```

如果 CLI 正常但仍无响应，增加超时时间：

```env
CLAUDE_TIMEOUT_SECONDS=600
```

### Q: Docker 容器无法连接 NapCat

确认 `.env` 中使用了正确的地址：

```env
# 错误（容器内不可达 127.0.0.1 宿主机服务）
ONEBOT_WS_URL=ws://127.0.0.1:3001

# 正确
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

### Q: 消息发送失败

1. 确认 OneBot WebSocket 连接正常：`./start.sh --status`
2. 确认 NapCat QQ 已登录且在线
3. 检查消息长度是否超过 `QQ_REPLY_CHUNK_SIZE`（自动分块发送）

### Q: 通知消息未收到

1. 检查 `CLAUDE_NOTIFY_ENABLED=true`
2. 确认 `CLAUDE_NOTIFY_QQ_IDS` 或 `ADMIN_QQ_IDS` 配置正确
3. 手动测试：`.venv/bin/python scripts/claude_notify_hook.py send "测试"`
4. 查看 `data/notify-state/` 下的状态文件

### Q: WorkerPool 未启动

检查配置：

```env
WORKER_POOL_ENABLED=true
```

查看日志确认启动：

```bash
grep "WorkerPool" logs/agent-qq.log
```

### Q: 任务一直在 pending 状态

1. 确认 WorkerPool 已启动：`grep "WorkerPool started" logs/agent-qq.log`
2. 确认有 idle Worker：`cat data/worker_state.json`
3. 确认 TaskScheduler 运行中：`grep "TaskScheduler started" logs/agent-qq.log`
4. 手动检查任务队列：`cat data/task_queue.json`

### Q: 如何更新 agent-qq

```bash
cd agent-qq
git pull
source .venv/bin/activate
pip install -r requirements.txt
./start.sh --restart
```

### Q: 如何彻底卸载

```bash
# 停止所有进程
./start.sh --stop

# 删除 systemd 服务（如已配置）
systemctl --user stop agent-qq.service
systemctl --user disable agent-qq.service
rm ~/.config/systemd/user/agent-qq.service

# 删除项目目录
cd .. && rm -rf agent-qq
```

---

## 附录：启动流程详解

```
./start.sh
  │
  ├─ 1. 检查 Python 解释器
  │
  ├─ 2. 检查已有实例（防双开）
  │
  ├─ 3. 检测 NapCat/QQ
  │     ├─ 已运行 → 跳过
  │     └─ 未运行 → 启动 NapCat（如启动器存在）
  │
  ├─ 4. 等待 OneBot WebSocket 端口 (:3001)
  │     └─ 超时 180s → 报错退出
  │
  ├─ 5. 启动 bot.py
  │
  ├─ 6. bot.py 启动后:
  │     ├─ 读取 .env 配置
  │     ├─ 初始化日志系统
  │     ├─ 初始化 TaskStatusLog（清理过期条目）
  │     ├─ 初始化 TaskRegistry + ClaudeClient + PlanStateMachine
  │     ├─ 初始化 CircuitBreaker
  │     ├─ 初始化 CommandRouter + MessageDeduplicator
  │     ├─ 启动 TaskMonitor（后台健康检查，每 5 秒）
  │     ├─ 初始化 Worker 状态（如首次启动）
  │     ├─ 运行 TaskRecovery（修复孤儿任务和 Worker）
  │     ├─ 启动 WorkerPool（子进程，4 Worker 并行）
  │     ├─ 启动 TaskScheduler（daemon 线程，1s 轮询）
  │     ├─ 启动 TaskCleaner（daemon 线程，5min 清理）
  │     └─ 连接 OneBot WebSocket → 进入事件循环
  │
  └─ 7. 验证运行状态
        └─ 主进程 + WorkerPool + 调度器 + 清理器 + OneBot
```

---

> 更多信息请查阅 [README.md](README.md) 和项目 `docs/` 目录。
