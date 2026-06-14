# agent-qq

基于 NapCat QQ + OneBot v11 + Claude Code CLI 的 QQ AI Agent 系统。通过纯脚本命令路由实现零 AI Token 消耗的命令处理，仅 `/plan`（计划管理）允许调用 AI 生成执行大纲。

内置 **多进程 Worker 池**，支持并行任务调度执行。

## 架构

```
QQ 用户
  ↕ 私聊消息
NapCat QQ (OneBot v11 WebSocket)
  ↕ ws://127.0.0.1:3001
┌──────────────────────────────────────────┐
│  bot.py (主进程, asyncio)                 │
│  ├── command_router.py   命令路由（纯脚本） │
│  ├── claude_client.py    Claude CLI 调用   │
│  ├── plan_state.py       计划状态机        │
│  ├── circuit_breaker.py  熔断保护          │
│  ├── task_monitor.py     后台任务监控      │
│  ├── task_registry.py    任务注册          │
│  ├── task_scheduler.py   任务调度 (线程)   │
│  ├── task_cleaner.py     过期清理 (线程)   │
│  ├── task_recovery.py    启动恢复          │
│  └── notifications/      QQ 通知系统       │
├──────────────────────────────────────────┤
│  WorkerPool (子进程, multiprocessing)      │
│  ├── Worker 1  ──── Claude CLI             │
│  ├── Worker 2  ──── Claude CLI             │
│  ├── Worker 3  ──── Claude CLI             │
│  └── Worker 4  ──── Claude CLI             │
└──────────────────────────────────────────┘
        ↕
Claude Code CLI → Anthropic API
```

## 核心设计原则

- **纯脚本命令路由** — 除 `/plan` 外，所有命令均由纯 Python 脚本处理，零 AI Token 消耗
- **计划状态机** — `/plan` 仅生成执行大纲（不实际执行），用户确认后才执行
- **多进程 Worker 池** — 4 个并行 Worker 执行 Claude CLI 任务，突破单进程限制
- **任务调度器** — 自动将 pending 任务分配给空闲 Worker，无需手动干预
- **熔断保护** — 自动检测 Token 耗尽、网络异常、任务超时，触发熔断与回滚
- **启动恢复** — 重启时自动修复孤儿任务和 Worker 状态
- **原子存储** — filelock + 原子写入保障 JSON 数据文件跨进程安全
- **消息去重** — 进程内消息去重，防止重复处理

## 可用命令

### 计划管理（唯一 AI 交互入口）

| 命令 | 说明 |
|------|------|
| `/plan <任务描述>` | 生成 AI 执行大纲（不实际执行） |
| `/plan-status` | 查看待确认的计划 |
| `/plan-start` | 确认并执行待确认计划 |
| `/plan-cancel` | 取消待确认计划 |
| `/plan-log` | 查看历史计划日志 |

### 任务控制

| 命令 | 说明 |
|------|------|
| `/status` | 查看运行状态和任务列表 |
| `/stop <ID或关键词>` | 停止运行中的任务 |
| `/kill <ID或关键词>` | 同 /stop（强制终止） |

### 管理员命令

| 命令 | 说明 |
|------|------|
| `/shell <命令>` | 执行白名单 Shell 命令 |
| `/log` | 查看日志文件位置 |

### 系统工具

| 命令 | 说明 |
|------|------|
| `/ping` | 心跳检测 |
| `/network` | 网络环境测试（优/良/差） |
| `/weather` | 手动触发天气推送 |
| `/clear` | 重置对话上下文 |
| `/token` | 查询当前 Token 预算 |
| `/help` | 查看完整命令列表 |

> 除 `/plan` 外，所有命令均由纯脚本执行，**零 AI Token 消耗**。未知消息不会传给 AI，会返回 `/help` 引导提示。

## 快速开始

### 1. 环境要求

- Python 3.11+
- [NapCat QQ](https://github.com/NapNeko/NapCatQQ)（已配置 OneBot v11 WebSocket）
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)（已登录并配置模型）
- （可选）Docker + Docker Compose

### 2. 配置

```bash
cd agent-qq
cp .env.example .env   # 或直接创建 .env
```

编辑 `.env`，最少配置：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
ADMIN_QQ_IDS=你的QQ号
ENABLE_PRIVATE_CHAT=true
```

### 3. 一键启动

```bash
./start.sh              # 启动（已有实例则跳过）
./start.sh --restart    # 重启
./start.sh --stop       # 停止
./start.sh --status     # 查看状态
```

脚本自动完成：NapCat 检测 → 等待 OneBot 端口 → 启动恢复（修复孤儿任务）→ 启动 WorkerPool（4 进程）→ 启动 TaskScheduler → 启动 TaskCleaner → 验证运行状态。

> 启动后看到 **2 个 bot.py 进程**是正常的：主进程（事件循环 + 调度器） + WorkerPool 子进程（并行 Worker）。

### 4. 手动启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 5. Docker 部署

```bash
docker compose up -d --build
docker compose logs -f agent-qq
```

## NapCat / OneBot 配置

在 NapCat WebUI（默认 `http://127.0.0.1:6099`）中启用 OneBot v11 WebSocket Server：

- 监听地址：`0.0.0.0`（或 `127.0.0.1`）
- 监听端口：`3001`
- Access Token：可选

Docker 部署时，`.env` 中使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

## 通知系统

agent-qq 内置 Claude Code Hook QQ 通知系统，可独立于 `bot.py` 运行：

```text
notifications/              # 通知模块（事件、格式化、限流、发送）
scripts/claude_notify_hook.py   # Hook 入口（monitor / stage / send）
```

功能：
- 任务开始/阶段变化/失败通知
- 长任务心跳通知
- 本轮完成汇总
- 频率限制与去重

配置集中在 `.env`，前缀 `CLAUDE_NOTIFY_*`。

## 项目结构

```
agent-qq/
├── bot.py                  # 主入口（asyncio 事件循环 + 组件编排）
├── config.py               # 配置管理（pydantic-settings + .env）
├── qq_client.py            # OneBot v11 WebSocket 客户端
├── claude_client.py        # Claude Code CLI 调用封装
├── command_router.py       # 命令路由 + 消息去重
├── circuit_breaker.py      # 熔断保护（Token耗尽/网络异常/超时）
├── plan_state.py           # 计划状态机（/plan 生命周期）
├── task_registry.py        # 任务注册与生命周期管理
├── task_monitor.py         # 后台任务健康监控（纯脚本，零 Token）
├── task_status_log.py      # 持久化任务状态日志
├── storage_manager.py      # 原子 JSON 存储（filelock + 原子写入）
├── worker_pool.py          # 多进程 Worker 池（并行执行 Claude CLI）
├── task_scheduler.py       # 任务调度器（pending → idle worker）
├── task_recovery.py        # 启动恢复（修复孤儿任务）
├── task_cleaner.py         # 过期任务清理（daemon 线程）
├── log_rotator.py          # 日志轮转清理
├── start.sh                # 一键启动脚本 v2
├── scripts/
│   ├── start_agent_qq.sh   # 完整启动脚本（含 NapCat 编排）
│   ├── claude_notify_hook.py   # Hook 入口（monitor / stage / send）
│   ├── check_onebot.py     # OneBot 连接检测工具
│   └── send_test_private_msg.py  # 私聊测试工具
├── notifications/          # QQ 通知模块（Hook 驱动）
│   ├── events.py           # 事件定义
│   ├── formatter.py        # 消息格式化
│   ├── limiter.py          # 频率限制
│   ├── sender.py           # 消息发送
│   ├── state.py            # 状态管理
│   └── service.py          # 服务入口
├── plugins/                # 插件目录（MCP / RAG 预留）
├── agents/                 # 多 Agent 扩展目录
├── tests/                  # 测试用例
├── docs/                   # 文档
├── deploy/                 # 部署配置（systemd 等）
├── data/                   # 运行时数据
│   ├── pending_plan.json   # 待确认计划
│   ├── plan_history.json   # 计划历史
│   ├── task_status_log.json # 任务状态日志
│   ├── task_queue.json     # 任务队列（Worker 调度用）
│   └── worker_state.json   # Worker 状态
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 测试

```bash
# 安装依赖后
.venv/bin/python -m pytest -q

# 仅语法检查
python3 -m compileall .
```

### OneBot 连接测试

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001
.venv/bin/python scripts/send_test_private_msg.py --to QQ号 --message "测试"
```

## 扩展预留

以下命令接口已预留，当前版本返回"尚未实现"：

| 命令 | 规划用途 |
|------|----------|
| `/search` | 搜索工具接入 |
| `/agent` | 多 Agent 调度 |
| `/mcp` | MCP 协议工具接入 |
| `/rag` | 知识库检索 |
| `/workflow` | 工作流编排 |

## 许可证

MIT
