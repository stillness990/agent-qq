# SOP：agent-qq 完整部署、运行、通知与运维标准操作流程

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | agent-qq 完整 SOP |
| 适用项目 | `/opt/agent-qq` |
| 适用版本依据 | 当前项目代码、`README.md`、`docs/`、`Dockerfile`、`docker-compose.yml`、`deploy/systemd/`、`notifications/`、`scripts/` |
| 适用环境 | Ubuntu/Linux、Docker Compose、本地 Python 虚拟环境、systemd 服务 |
| 核心组件 | NapCat QQ、OneBot v11 WebSocket、agent-qq Python Gateway、Claude Code CLI、Claude Code Hooks QQ 通知 |
| 推荐生产方式 | Docker Compose；需要 systemd 托管本地进程时使用 `deploy/systemd/agent-qq.service` |
| 重要边界 | Python 业务层不直接调用 Anthropic API；智能能力由本机 `claude` CLI 提供 |

## 2. 核心结论

`agent-qq` 是一个 QQ 私聊 AI Agent 网关：用户通过 QQ 私聊机器人，NapCat 将消息转换为 OneBot v11 WebSocket 事件，`agent-qq` 解析命令并通过 Claude Code CLI 执行智能任务，再通过 OneBot 将结果返回 QQ。

当前项目还内置了 Claude Code Hook QQ 通知系统：Claude Code 执行任务时，可通过 `scripts/claude_notify_hook.py` 独立向管理员 QQ 推送开始、阶段、失败、长任务心跳和完成汇总通知。通知系统不依赖 `bot.py` 主进程在线，只依赖 NapCat / OneBot WebSocket 可用。

## 3. 系统架构

### 3.1 QQ AI Agent 主链路

```text
用户 QQ 私聊
  ↓
机器人 QQ / NapCat QQ
  ↓
OneBot v11 WebSocket Server
  ↓
agent-qq WebSocket Client（qq_client.py）
  ↓
消息去重与私聊解析（command_router.py）
  ↓
命令路由与权限控制（CommandRouter）
  ↓
Claude Code CLI 调用封装（claude_client.py：claude -p）
  ↓
本机 Claude Code 已配置模型
  ↓
OneBot send_private_msg 返回 QQ 私聊
```

### 3.2 Claude Code QQ 通知链路

```text
Claude Code Hooks
  ↓
scripts/claude_notify_hook.py
  ↓
notifications/events.py      解析 Hook JSON
notifications/formatter.py   阶段分类与文案格式化
notifications/limiter.py     防轰炸限流
notifications/state.py       状态文件与锁文件
notifications/sender.py      QQ 私聊发送
notifications/service.py     通知事件编排
  ↓
config.py + qq_client.py
  ↓
NapCat / OneBot v11 WebSocket
  ↓
管理员 QQ 私聊
```

### 3.3 组件职责

| 组件 | 文件/位置 | 职责 |
|---|---|---|
| 主程序入口 | `bot.py` | 初始化配置、日志、Claude 客户端、命令路由、OneBot 客户端，维持重连循环 |
| 配置系统 | `config.py` | 从 `.env` 读取 OneBot、Claude CLI、权限、日志、通知限流等配置 |
| OneBot 客户端 | `qq_client.py` | 连接 NapCat OneBot v11 WebSocket，接收事件，发送私聊，支持分段回复 |
| Claude CLI 封装 | `claude_client.py` | 执行 `claude -p <prompt>`，处理超时、stderr、工作目录 |
| 命令路由 | `command_router.py` | `/help`、`/status`、`/ask`、`/log`、`/shell`、`/code` 与预留命令 |
| 通知模块 | `notifications/` | Hook 事件解析、通知文案、限流、状态、发送与长任务监控 |
| Hook 入口 | `scripts/claude_notify_hook.py` | Claude Code Hook 调用入口，支持 `send/start/stage/success/failure/stop/monitor/cleanup` |
| OneBot 检查 | `scripts/check_onebot.py` | 测试 WebSocket 是否可连接 |
| 私聊推送测试 | `scripts/send_test_private_msg.py` | 直接通过 OneBot 向指定 QQ 发送测试私聊 |
| 本地启动脚本 | `scripts/start_agent_qq.sh` | 辅助启动 NapCat 与本地 `bot.py` |
| systemd 服务 | `deploy/systemd/agent-qq.service` | 本地长期运行 `bot.py` 的 systemd unit |
| systemd 注册脚本 | `deploy/register-agent-qq-service.sh` | 安装并启用 systemd 服务 |
| Docker 镜像 | `Dockerfile` | Python 3.12 slim，安装 Node/npm、Claude Code CLI、Python 依赖 |
| Docker 编排 | `docker-compose.yml` | 构建、挂载日志/插件/agents/Claude 配置，连接宿主机 NapCat |

## 4. 当前项目目录结构

```text
agent-qq/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── bot.py
├── config.py
├── qq_client.py
├── claude_client.py
├── command_router.py
├── agents/
│   ├── __init__.py
│   └── base.py
├── plugins/
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── base.py
│   └── rag/
│       ├── __init__.py
│       └── base.py
├── notifications/
│   ├── __init__.py
│   ├── events.py
│   ├── formatter.py
│   ├── limiter.py
│   ├── sender.py
│   ├── service.py
│   └── state.py
├── scripts/
│   ├── check_onebot.py
│   ├── claude_notify_hook.py
│   ├── send_test_private_msg.py
│   └── start_agent_qq.sh
├── deploy/
│   ├── register-agent-qq-service.sh
│   └── systemd/
│       └── agent-qq.service
├── tests/
│   ├── test_command_router.py
│   └── test_notifications.py
├── docs/
│   ├── agent-qq-install-deploy-sop.md
│   ├── claude-notify-project-plan.md
│   ├── claude-qq-notify-sop.md
│   └── agent-qq-complete-sop.md
├── logs/                  # 运行日志，不提交
├── data/notify-state/     # 通知运行状态，不提交
└── workspace/             # 推荐作为 Claude 工作区，不提交
```

> 注意：`logs/`、`data/notify-state/`、`workspace/`、`.env`、`.venv/`、`.claude/`、`guild1.db*` 均属于运行时或本地敏感文件，应保持在 Git 忽略范围内。

## 5. 安全边界与关键原则

1. **不在 Python 代码中直接调用 Anthropic API**：当前智能能力统一经由 Claude Code CLI：`claude -p`。
2. **不在 `.env` 中配置 `ANTHROPIC_API_KEY`**：Claude 登录、模型、权限和认证由宿主机 Claude Code CLI / `~/.claude` 管理。
3. **Docker 中只读挂载 Claude 配置目录**：`${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro`。
4. **管理员权限必须严格配置**：`/shell`、`/code`、`/log` 仅管理员可用。
5. **Shell 命令必须白名单控制**：生产环境不要放行 `rm`、`curl`、`wget`、`ssh`、`scp`、`bash`、`sh`、`sudo`、`chmod`、`chown` 等高风险前缀。
6. **通知系统失败不得阻断 Claude Code 主任务**：Hook 命令建议追加 `2>/dev/null || true`。
7. **通知必须限流降噪**：默认启用阶段冷却、失败冷却、全局预算、单会话预算和长任务心跳。
8. **防回环**：`command_router.py` 会忽略机器人自身消息和以 `【Claude】` 开头的通知消息。

## 6. 前置条件

### 6.1 基础环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Ubuntu/Linux |
| Python | 本地运行推荐 Python 3.11+；Docker 镜像使用 Python 3.12 slim |
| Docker / Compose | 推荐生产部署方式需要 Docker Engine + Docker Compose v2 |
| Node.js/npm | Dockerfile 内安装；宿主机安装 Claude Code CLI 时需要 |
| Git | 更新代码、回滚、排障建议安装 |
| NapCat QQ | 已安装并能登录机器人 QQ |
| OneBot v11 | NapCat 中启用 WebSocket Server |
| Claude Code CLI | 宿主机已安装、已登录、能执行 `claude -p` |

### 6.2 必备信息

| 信息 | 示例 | 说明 |
|---|---|---|
| 机器人 QQ | `<bot_qq_id>` | NapCat 登录账号 |
| 管理员 QQ | `<admin_qq_id>` | `ADMIN_QQ_IDS`，不是机器人 QQ |
| OneBot WebSocket 地址 | `ws://127.0.0.1:3001` / `ws://host.docker.internal:3001` | 本地或 Docker 场景不同 |
| OneBot Token | 可为空 | NapCat 配置了 access_token 时必须一致 |
| Claude 配置目录 | `<CLAUDE_CONFIG_DIR>` | Docker 挂载到容器 `/root/.claude:ro` |
| Claude 工作目录 | `/workspace` 或 `/opt/agent-qq/workspace` | Claude CLI 与 `/shell` 的执行目录 |
| 通知状态目录 | `data/notify-state` | 存放 session/global 状态与 monitor lock |

## 7. 配置文件说明

### 7.1 最小 `.env` 模板

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ONEBOT_ACCESS_TOKEN=
ENABLE_PRIVATE_CHAT=true
ADMIN_QQ_IDS=<ADMIN_QQ_ID>

CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
CLAUDE_CONFIG_DIR=/home/your-user/.claude

ENABLE_SHELL_COMMAND=false
SHELL_ALLOWED_PREFIXES=pwd,ls,git status,python --version,python3 --version,df -h,free -h,whoami,uname -a

MESSAGE_DEDUPE_TTL_SECONDS=300
LOG_LEVEL=INFO
RECONNECT_INITIAL_SECONDS=2
RECONNECT_MAX_SECONDS=60
QQ_REPLY_CHUNK_SIZE=1800

CLAUDE_NOTIFY_ENABLED=true
CLAUDE_NOTIFY_QQ_IDS=
CLAUDE_NOTIFY_PREFIX=【Claude】
CLAUDE_NOTIFY_STATE_DIR=data/notify-state
CLAUDE_NOTIFY_MESSAGE_MAX_LEN=180
CLAUDE_NOTIFY_STAGE_COOLDOWN_SECONDS=60
CLAUDE_NOTIFY_SUCCESS_MODE=important
CLAUDE_NOTIFY_FAILURE_COOLDOWN_SECONDS=180
CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS=8
CLAUDE_NOTIFY_MAX_PER_10_MINUTES=20
CLAUDE_NOTIFY_MAX_PER_HOUR=60
CLAUDE_NOTIFY_SESSION_BUDGET=25
CLAUDE_NOTIFY_START_DEDUPE_SECONDS=30
CLAUDE_NOTIFY_STOP_DEDUPE_SECONDS=30
CLAUDE_NOTIFY_LONG_TASK_SECONDS=600
CLAUDE_NOTIFY_HEARTBEAT_SECONDS=300
CLAUDE_NOTIFY_MONITOR_INTERVAL_SECONDS=30
CLAUDE_NOTIFY_MONITOR_LOCK_TTL_SECONDS=120
CLAUDE_NOTIFY_STATE_TTL_SECONDS=86400
CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES=
```

### 7.2 主服务配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ONEBOT_WS_URL` | `ws://127.0.0.1:3001` | NapCat OneBot v11 WebSocket 地址 |
| `ONEBOT_ACCESS_TOKEN` | 空 | OneBot Bearer token；NapCat 配置 token 时填写 |
| `ENABLE_PRIVATE_CHAT` | `true` | 是否响应私聊消息 |
| `ADMIN_QQ_IDS` | 空集合 | 管理员 QQ，多个用英文逗号分隔 |
| `CLAUDE_CLI_COMMAND` | `claude` | Claude Code CLI 命令名或绝对路径 |
| `CLAUDE_TIMEOUT_SECONDS` | `180` | Claude CLI 与 `/shell` 单次执行超时秒数 |
| `CLAUDE_WORKDIR` | `/workspace` | Claude CLI 和 `/shell` 的工作目录；程序会自动创建 |
| `ENABLE_SHELL_COMMAND` | `false` | 是否启用 `/shell` 命令 |
| `SHELL_ALLOWED_PREFIXES` | `pwd,ls` | `/shell` 允许的命令前缀 |
| `MESSAGE_DEDUPE_TTL_SECONDS` | `300` | OneBot 消息去重 TTL |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `RECONNECT_INITIAL_SECONDS` | `2` | OneBot 首次重连等待 |
| `RECONNECT_MAX_SECONDS` | `60` | OneBot 最大重连等待 |
| `QQ_REPLY_CHUNK_SIZE` | `1800` | QQ 私聊分段长度 |

### 7.3 通知配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CLAUDE_NOTIFY_ENABLED` | `true` | 是否启用 Claude Code QQ 通知 |
| `CLAUDE_NOTIFY_QQ_IDS` | 空 | 通知接收 QQ；为空回退到 `ADMIN_QQ_IDS` |
| `CLAUDE_NOTIFY_PREFIX` | `【Claude】` | 通知消息前缀，也是回环防护前缀 |
| `CLAUDE_NOTIFY_STATE_DIR` | `data/notify-state` | 通知状态目录 |
| `CLAUDE_NOTIFY_MESSAGE_MAX_LEN` | `180` | 单条通知最大长度 |
| `CLAUDE_NOTIFY_STAGE_COOLDOWN_SECONDS` | `60` | 同阶段通知冷却 |
| `CLAUDE_NOTIFY_SUCCESS_MODE` | `important` | `off` / `important` / `all`；默认只通知重要成功 |
| `CLAUDE_NOTIFY_FAILURE_COOLDOWN_SECONDS` | `180` | 相同失败冷却 |
| `CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS` | `8` | 同一接收人全局最小间隔 |
| `CLAUDE_NOTIFY_MAX_PER_10_MINUTES` | `20` | 同一接收人 10 分钟预算 |
| `CLAUDE_NOTIFY_MAX_PER_HOUR` | `60` | 同一接收人小时预算 |
| `CLAUDE_NOTIFY_SESSION_BUDGET` | `25` | 单 session 通知预算 |
| `CLAUDE_NOTIFY_START_DEDUPE_SECONDS` | `30` | start 去重窗口 |
| `CLAUDE_NOTIFY_STOP_DEDUPE_SECONDS` | `30` | stop 去重窗口 |
| `CLAUDE_NOTIFY_LONG_TASK_SECONDS` | `600` | 长任务首次提醒阈值 |
| `CLAUDE_NOTIFY_HEARTBEAT_SECONDS` | `300` | 长任务心跳间隔 |
| `CLAUDE_NOTIFY_MONITOR_INTERVAL_SECONDS` | `30` | monitor 检查间隔 |
| `CLAUDE_NOTIFY_MONITOR_LOCK_TTL_SECONDS` | `120` | monitor 锁 TTL |
| `CLAUDE_NOTIFY_STATE_TTL_SECONDS` | `86400` | session 状态清理 TTL |
| `CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES` | 空 | 可选：限制哪些 cwd 的 Claude Code 任务触发通知 |

## 8. Claude / Anthropic 集成核对清单

### 8.1 当前项目的真实集成方式

当前项目不是 Anthropic SDK 应用，也不是直接调用 `/v1/messages` 的应用。它通过本地 Claude Code CLI 调用：

```text
claude -p <prompt>
```

因此：

1. Python 依赖中不需要 `anthropic` SDK。
2. `.env` 不需要 `ANTHROPIC_API_KEY`。
3. 模型 ID、登录态、权限、MCP、工具、Claude Code 设置由宿主机 Claude Code 环境决定。
4. Docker 场景通过只读挂载宿主机 Claude 配置目录，让容器内 `claude` 命令复用登录配置。

### 8.2 必须核对的 Claude Code 项

| 检查项 | 命令/动作 | 预期 |
|---|---|---|
| CLI 安装 | `claude --version` | 输出版本号 |
| CLI 登录 | `claude -p "你好，请只回复 OK"` | 正常返回 `OK` 或等价内容 |
| 宿主机配置目录 | `CLAUDE_CONFIG_DIR=/home/your-user/.claude` | 目录存在，且为当前已登录配置 |
| Docker 挂载 | `docker compose exec agent-qq claude --version` | 容器内能执行 `claude` |
| Docker 内调用 | `docker compose exec agent-qq claude -p "你好，请只回复 OK"` | 容器内正常返回 |
| 模型选择 | 在 Claude Code 配置中确认 | 由 Claude Code 当前配置决定，业务代码不指定 |
| Hook 配置 | `~/.claude/settings.json` 或 `/hooks` | Hook 命令指向本项目脚本 |

### 8.3 模型与 API 注意事项

虽然本项目不直接写模型 ID，但若后续扩展为直接调用 Anthropic API 或在 Claude Code 配置中显式指定模型，应遵循：

1. 默认优先使用当前 Claude Code 支持的最新高能力模型；模型选择不要写死在 `agent-qq` 业务代码中。
2. 若直接接入 Anthropic SDK，新代码应使用官方 SDK，不要混用 OpenAI 兼容层。
3. 新 Claude API 代码应使用准确模型 ID，例如 `claude-opus-4-8`；不要自行拼接日期后缀。
4. Opus 4.8 / 4.7 / Fable 5 等新模型使用 `thinking: {type: "adaptive"}`，不要使用已移除的 `budget_tokens`。
5. 新模型不支持 `temperature`、`top_p`、`top_k` 等采样参数时，应删除这些参数，通过提示词和 `output_config.effort` 控制行为。
6. 长输出应使用 streaming；直接 API 场景中 `max_tokens` 很大时不要非流式调用。
7. 对工具调用输入必须解析 JSON，不要对序列化字符串做脆弱匹配。

### 8.4 Claude Code Hook 命令建议

在 Claude Code Hook 配置中，建议将命令写成绝对路径，并允许失败不影响主任务：

```bash
/opt/agent-qq/scripts/claude_notify_hook.py start 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py stage 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py success 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py failure 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py stop 2>/dev/null || true
```

推荐 Hook 事件映射：

| Claude Code Hook | 本项目命令 | 作用 |
|---|---|---|
| `UserPromptSubmit` | `start` | 任务开始通知，并启动 monitor |
| `PreToolUse` | `stage` | 工具执行前阶段通知 |
| `PostToolUse` | `success` | 工具成功后记录/按策略通知 |
| `PostToolUseFailure` | `failure` | 工具失败通知 |
| `Stop` | `stop` | 本轮完成汇总 |

## 9. 标准部署流程：Docker Compose 推荐

### 9.1 准备 NapCat / OneBot

1. 启动 NapCat QQ。
2. 使用机器人 QQ 登录。
3. 在 NapCat WebUI 启用 OneBot v11 WebSocket Server。
4. 推荐配置：

```text
Host: 0.0.0.0
Port: 3001
Access Token: 生产环境建议填写随机长字符串
```

5. 宿主机验证端口：

```bash
ss -ltn | grep 3001
```

预期：看到 3001 端口监听。

### 9.2 准备项目配置

```bash
cd /opt/agent-qq
cp .env.example .env
nano .env
```

Docker 场景重点确认：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
CLAUDE_CONFIG_DIR=/home/your-user/.claude
CLAUDE_WORKDIR=/workspace
```

如果 NapCat 设置了 token：

```env
ONEBOT_ACCESS_TOKEN=<ONEBOT_ACCESS_TOKEN>
```

### 9.3 验证宿主机 Claude Code CLI

```bash
claude --version
claude -p "你好，请只回复 OK"
```

如果失败，先在宿主机完成 Claude Code 登录与配置，再继续。

### 9.4 构建并启动

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f agent-qq
```

预期日志包含：

```text
Connected to OneBot: ws://host.docker.internal:3001
```

### 9.5 Docker 内 Claude 验证

```bash
docker compose exec agent-qq claude --version
docker compose exec agent-qq claude -p "你好，请只回复 OK"
```

如果容器内失败，重点检查：

1. `CLAUDE_CONFIG_DIR` 是否指向宿主机真实 Claude 配置目录。
2. `docker-compose.yml` 是否挂载 `${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro`。
3. 宿主机 Claude Code 是否已登录。
4. Dockerfile 是否已成功安装 `@anthropic-ai/claude-code`。

## 10. 本地 Python 调试流程

### 10.1 创建虚拟环境

```bash
cd /opt/agent-qq
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果系统没有可用 `pip` / `ensurepip`，可使用 `uv`：

```bash
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

### 10.2 本地 `.env` 重点配置

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/opt/agent-qq/workspace
```

### 10.3 OneBot 连通性预检

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001
```

带 token：

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001 --token <ONEBOT_ACCESS_TOKEN>
```

预期：

```text
ok: connected to ws://127.0.0.1:3001
```

### 10.4 启动主程序

前台运行：

```bash
.venv/bin/python bot.py
```

使用辅助脚本后台运行：

```bash
scripts/start_agent_qq.sh background
```

前台脚本运行：

```bash
scripts/start_agent_qq.sh --foreground
```

## 11. systemd 部署流程（可选）

适用于不使用 Docker、希望本机 Python 进程由 systemd 托管的场景。

### 11.1 前置检查

确认以下文件存在：

```text
/opt/agent-qq/.venv/bin/python
/opt/agent-qq/bot.py
/opt/agent-qq/deploy/systemd/agent-qq.service
```

### 11.2 注册服务

```bash
cd /opt/agent-qq
sudo bash deploy/register-agent-qq-service.sh
```

脚本会：

1. 检查 Python 与 `bot.py`。
2. 停止可能已有的手动 `bot.py` 进程。
3. 安装 unit 到 `/etc/systemd/system/agent-qq.service`。
4. `systemctl daemon-reload`。
5. 设置开机自启。
6. 重启服务并显示状态。

### 11.3 常用 systemd 命令

```bash
sudo systemctl status agent-qq --no-pager
journalctl -u agent-qq -f
sudo systemctl restart agent-qq
sudo systemctl stop agent-qq
```

## 12. QQ 命令说明

| 命令 | 权限 | 行为 |
|---|---|---|
| `/help` | 所有私聊用户 | 返回命令帮助 |
| `/status` | 所有私聊用户 | 返回运行状态、管理员状态、私聊开关、Shell 开关、Claude CLI 状态 |
| `/ask <问题>` | 所有私聊用户 | 调用 Claude Code CLI 回答 |
| 普通私聊文本 | 所有私聊用户 | 等价于 `/ask` |
| `/log` | 管理员 | 返回日志位置提示 |
| `/shell <命令>` | 管理员 + Shell 开启 + 白名单 | 执行白名单 Shell 命令 |
| `/code <需求>` | 管理员 | 用谨慎代码助手提示词调用 Claude Code |
| `/search` `/agent` `/mcp` `/rag` `/workflow` | 预留 | 当前返回“尚未实现” |

## 13. 部署后验证与验收

### 13.1 端到端验收表

| 检查项 | 命令/动作 | 预期结果 |
|---|---|---|
| NapCat 在线 | 查看 NapCat WebUI | 机器人 QQ 在线 |
| OneBot 监听 | `ss -ltn \| grep 3001` | 端口监听 |
| OneBot 连通 | `.venv/bin/python scripts/check_onebot.py` | 输出 `ok` |
| Claude 宿主机可用 | `claude -p "你好"` | 正常返回 |
| Docker 服务 | `docker compose ps` | `agent-qq` Up |
| Docker 日志 | `docker compose logs -f agent-qq` | 出现 `Connected to OneBot` |
| Docker Claude | `docker compose exec agent-qq claude -p "你好"` | 正常返回 |
| QQ 帮助 | 私聊 `/help` | 返回命令列表 |
| QQ 状态 | 私聊 `/status` | 返回运行状态与 Claude CLI 状态 |
| Claude 问答 | 私聊 `/ask 你好，请只回复 OK` | 返回 Claude 答复 |
| 管理员 Shell | 私聊 `/shell pwd` | 管理员可执行白名单命令 |
| 通知手测 | `.venv/bin/python scripts/claude_notify_hook.py send "【Claude】测试"` | 管理员 QQ 收到通知 |

### 13.2 OneBot 私聊推送测试

```bash
.venv/bin/python scripts/send_test_private_msg.py --to <ADMIN_QQ_ID> --message "agent-qq OneBot 推送测试"
```

带 token：

```bash
.venv/bin/python scripts/send_test_private_msg.py --to <ADMIN_QQ_ID> --token <ONEBOT_ACCESS_TOKEN>
```

预期：目标 QQ 收到测试私聊，命令行输出：

```text
sent
```

## 14. Claude Code QQ 通知系统部署

### 14.1 启用通知配置

确认 `.env`：

```env
CLAUDE_NOTIFY_ENABLED=true
CLAUDE_NOTIFY_QQ_IDS=
CLAUDE_NOTIFY_PREFIX=【Claude】
CLAUDE_NOTIFY_STATE_DIR=data/notify-state
```

如果 `CLAUDE_NOTIFY_QQ_IDS` 为空，通知接收人默认使用 `ADMIN_QQ_IDS`。

### 14.2 配置 Claude Code Hook

将 Claude Code Hook 命令指向：

```text
/opt/agent-qq/scripts/claude_notify_hook.py
```

示例命令：

```bash
/opt/agent-qq/scripts/claude_notify_hook.py start 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py stage 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py success 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py failure 2>/dev/null || true
/opt/agent-qq/scripts/claude_notify_hook.py stop 2>/dev/null || true
```

配置后，在 Claude Code 中执行 `/hooks` 或重启 Claude Code，使配置生效。

### 14.3 手动验证通知

发送普通测试消息：

```bash
cd /opt/agent-qq
.venv/bin/python scripts/claude_notify_hook.py send "【Claude】hook 测试消息"
```

模拟任务开始：

```bash
printf '{"session_id":"manual-test","prompt":"测试 Claude QQ 通知","cwd":"/opt/agent-qq"}' \
  | .venv/bin/python scripts/claude_notify_hook.py start
```

模拟阶段变化：

```bash
printf '{"session_id":"manual-test","tool_name":"Bash","tool_input":{"command":"pytest -q"}}' \
  | .venv/bin/python scripts/claude_notify_hook.py stage
```

模拟失败：

```bash
printf '{"session_id":"manual-test","tool_name":"Bash","error":"pytest failed"}' \
  | .venv/bin/python scripts/claude_notify_hook.py failure
```

模拟完成：

```bash
printf '{"session_id":"manual-test"}' \
  | .venv/bin/python scripts/claude_notify_hook.py stop
```

### 14.4 通知状态维护

状态目录：

```text
/opt/agent-qq/data/notify-state/
```

常见文件：

```text
global.json              # 接收人全局限流历史
<session_id>.json        # 单 session 状态
<session_id>.lock        # monitor 锁
```

手动清理过期状态：

```bash
.venv/bin/python scripts/claude_notify_hook.py cleanup
```

## 15. 测试流程

### 15.1 单元测试

```bash
cd /opt/agent-qq
.venv/bin/python -m pytest -q
```

### 15.2 语法检查

```bash
python3 -m compileall .
```

### 15.3 Docker 构建验证

```bash
docker compose build
```

### 15.4 推荐发布前检查

```bash
.venv/bin/python -m pytest -q
python3 -m compileall .
docker compose build
```

## 16. 常用运维操作

### 16.1 Docker 运维

```bash
docker compose ps
docker compose logs -f agent-qq
docker compose logs --tail=200 agent-qq
docker compose restart agent-qq
docker compose down
docker compose up -d --build
```

### 16.2 日志位置

| 日志 | 说明 |
|---|---|
| `logs/agent-qq.log` | Python 主程序滚动日志，最大 5MB，保留 5 个备份 |
| `logs/agent-qq.stdout.log` | 本地启动脚本后台运行 stdout/stderr |
| `logs/napcat.stdout.log` | 本地启动脚本启动 NapCat 的 stdout/stderr |
| `journalctl -u agent-qq -f` | systemd 部署日志 |
| `docker compose logs -f agent-qq` | Docker 部署日志 |

### 16.3 更新代码

```bash
cd /opt/agent-qq
git pull
docker compose up -d --build
docker compose logs -f agent-qq
```

### 16.4 修改配置后重启

`.env` 修改后必须重启：

```bash
docker compose restart agent-qq
```

或 systemd：

```bash
sudo systemctl restart agent-qq
```

## 17. 回滚流程

### 17.1 配置回滚

适用：`.env`、`docker-compose.yml`、Hook 设置、白名单配置变更后异常。

1. 恢复上一份可用配置。
2. 重启服务。
3. 查看日志。
4. QQ 私聊验证 `/status` 与 `/ask 你好`。

Docker：

```bash
docker compose restart agent-qq
docker compose logs -f agent-qq
```

systemd：

```bash
sudo systemctl restart agent-qq
journalctl -u agent-qq -f
```

### 17.2 代码回滚

```bash
git log --oneline -n 10
git checkout <last_good_commit>
docker compose up -d --build
```

验证完成后恢复分支：

```bash
git checkout <branch_name>
git pull
docker compose up -d --build
```

### 17.3 通知 Hook 回滚

若新 Hook 异常：

1. 临时关闭通知：

```env
CLAUDE_NOTIFY_ENABLED=false
```

2. 或在 Claude Code Hook 配置中临时移除/改回旧脚本。
3. 重启 Claude Code 或执行 `/hooks` 使配置生效。

## 18. 故障排查 Runbook

### 18.1 OneBot 连接失败

#### 症状

- 日志出现 OneBot connection failed。
- `scripts/check_onebot.py` 输出 `failed`。
- QQ 私聊无响应。

#### 排查

1. NapCat 是否启动并登录。
2. OneBot WebSocket Server 是否启用。
3. 端口是否监听：

```bash
ss -ltn | grep 3001
```

4. 本地运行时 `.env` 是否为：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

5. Docker 运行时 `.env` 是否为：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

6. Token 是否一致：

```env
ONEBOT_ACCESS_TOKEN=<ONEBOT_ACCESS_TOKEN>
```

#### 处理

- 修改 NapCat Host 为 `0.0.0.0`。
- 修正 OneBot URL / token。
- 重启 NapCat OneBot 服务。
- 重启 agent-qq。

### 18.2 Docker 容器无法连接宿主机 NapCat

#### 排查

1. NapCat 是否绑定 `0.0.0.0`。
2. `docker-compose.yml` 是否包含：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

3. `.env` 是否使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

#### 处理

```bash
docker compose up -d --build
```

### 18.3 `/status` 无回复

#### 排查

1. 查看日志：

```bash
docker compose logs --tail=200 agent-qq
```

2. 当前版本主要处理私聊，不处理群聊。
3. 确认发送者与机器人是私聊关系。
4. 确认：

```env
ENABLE_PRIVATE_CHAT=true
```

5. 确认 OneBot 上报 `message_type=private`。

### 18.4 `/ask` 超时或失败

#### 排查

宿主机：

```bash
claude -p "你好，请只回复 OK"
```

容器内：

```bash
docker compose exec agent-qq claude -p "你好，请只回复 OK"
```

检查 Claude 配置目录挂载：

```bash
docker compose exec agent-qq ls -la /root/.claude
```

检查超时时间：

```env
CLAUDE_TIMEOUT_SECONDS=180
```

#### 处理

- 宿主机重新登录 Claude Code。
- 修正 `CLAUDE_CONFIG_DIR`。
- 增加 `CLAUDE_TIMEOUT_SECONDS`。
- 重建容器。
- 对特别长的问题，提示用户缩短问题或拆分任务。

### 18.5 `/shell` 无法执行命令

原因通常是：

1. `ENABLE_SHELL_COMMAND=false`。
2. 用户不是管理员。
3. 命令不匹配 `SHELL_ALLOWED_PREFIXES`。

处理：

```env
ENABLE_SHELL_COMMAND=true
SHELL_ALLOWED_PREFIXES=pwd,ls,git status,python --version,python3 --version,df -h,free -h
```

修改后重启：

```bash
docker compose restart agent-qq
```

### 18.6 收不到 Claude Code QQ 通知

#### 排查

1. OneBot 是否可连接：

```bash
.venv/bin/python scripts/check_onebot.py
```

2. `.env` 是否配置接收人：

```env
ADMIN_QQ_IDS=<ADMIN_QQ_ID>
CLAUDE_NOTIFY_QQ_IDS=
```

3. 通知是否启用：

```env
CLAUDE_NOTIFY_ENABLED=true
```

4. Hook 路径是否正确：

```text
/opt/agent-qq/scripts/claude_notify_hook.py
```

5. 手动发送是否成功：

```bash
.venv/bin/python scripts/claude_notify_hook.py send "【Claude】测试"
```

6. 如果限制 cwd，确认当前任务目录满足：

```env
CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES=/opt/agent-qq,/opt/other-project
```

### 18.7 通知太多

调大冷却或降低成功通知：

```env
CLAUDE_NOTIFY_STAGE_COOLDOWN_SECONDS=120
CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS=20
CLAUDE_NOTIFY_SESSION_BUDGET=10
CLAUDE_NOTIFY_SUCCESS_MODE=off
```

然后重新触发 Hook 或重启相关 Claude Code 会话。

### 18.8 Hook 失败影响 Claude Code

Hook 命令必须写成容错形式：

```bash
/opt/agent-qq/scripts/claude_notify_hook.py stage 2>/dev/null || true
```

如需临时调试 Hook 错误：

```bash
CLAUDE_NOTIFY_DEBUG=1 /opt/agent-qq/scripts/claude_notify_hook.py send "【Claude】debug 测试"
```

### 18.9 日志文件不存在

确认目录：

```bash
mkdir -p /opt/agent-qq/logs
```

Docker 场景确认挂载：

```yaml
volumes:
  - ./logs:/app/logs
```

重启服务。

## 19. 安全检查清单

### 19.1 部署安全

- [ ] `.env` 未提交到仓库。
- [ ] `ONEBOT_ACCESS_TOKEN` 使用随机长字符串，且只在 NapCat 与 `.env` 中一致配置。
- [ ] `ADMIN_QQ_IDS` 只包含可信管理员。
- [ ] `ENABLE_SHELL_COMMAND` 生产默认关闭或严格按需开启。
- [ ] `SHELL_ALLOWED_PREFIXES` 不包含高危命令前缀。
- [ ] Docker 只读挂载 Claude 配置：`/root/.claude:ro`。
- [ ] Python 业务代码不包含 `ANTHROPIC_API_KEY`。
- [ ] `.env` 不包含 `ANTHROPIC_API_KEY`、Claude auth token、私有 base URL。
- [ ] `CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES` 按需限制全局 Hook 触发范围。
- [ ] Hook 命令包含 `2>/dev/null || true`，避免通知失败阻断主任务。

### 19.2 发布脱敏

不得提交：

```text
.env
.venv/
__pycache__/
.pytest_cache/
logs/
workspace/
guild1.db*
napcat_*.json
.claude/
data/notify-state/
notify-state/
```

发布前建议扫描：

```bash
rg -n "(ANTHROPIC_API_KEY|access_token|ONEBOT_ACCESS_TOKEN|ADMIN_QQ_IDS|password|secret|token|Bearer|[0-9]{6,})" . -S
find . -name '__pycache__' -o -name '*.pyc' -o -name '.env' -o -name 'guild1.db*'
```

命中后必须人工判断并移除真实 token、真实 QQ 号、真实路径敏感信息、日志和数据库。

## 20. 变更流程

### 20.1 修改代码

1. 建议先运行测试，确认基线：

```bash
.venv/bin/python -m pytest -q
```

2. 修改代码。
3. 运行测试和语法检查：

```bash
.venv/bin/python -m pytest -q
python3 -m compileall .
```

4. Docker 场景构建验证：

```bash
docker compose build
```

5. 部署并观察日志。
6. QQ 私聊执行 `/status`、`/ask 你好`。

### 20.2 修改 `.env`

1. 备份当前 `.env`。
2. 修改配置。
3. 重启服务。
4. 验证 `/status`、`/ask`、通知手测。

### 20.3 修改 Claude Code Hook

1. 先手动运行 `scripts/claude_notify_hook.py send`。
2. 修改 `~/.claude/settings.json` 或通过 Claude Code `/hooks` 配置。
3. Hook 命令必须为绝对路径。
4. 增加容错后缀 `2>/dev/null || true`。
5. 重启 Claude Code 或刷新 Hooks。
6. 用一次简单 Claude Code 任务观察通知。

## 21. 最小快速部署清单

1. 启动并登录 NapCat QQ。
2. 在 NapCat 启用 OneBot v11 WebSocket：

```text
Host: 0.0.0.0
Port: 3001
```

3. 验证宿主机 Claude Code：

```bash
claude --version
claude -p "你好"
```

4. 创建 `.env`：

```bash
cd /opt/agent-qq
cp .env.example .env
nano .env
```

5. 最小配置：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ENABLE_PRIVATE_CHAT=true
ADMIN_QQ_IDS=<ADMIN_QQ_ID>
CLAUDE_CONFIG_DIR=/home/your-user/.claude
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
```

6. 启动：

```bash
docker compose up -d --build
```

7. 查看日志：

```bash
docker compose logs -f agent-qq
```

8. QQ 私聊测试：

```text
/help
/status
/ask 你好，请只回复 OK
```

9. 通知测试：

```bash
.venv/bin/python scripts/claude_notify_hook.py send "【Claude】部署完成测试"
```

## 22. 后续扩展建议

| 方向 | 当前状态 | 建议 |
|---|---|---|
| MCP | `plugins/mcp/base.py` 预留 | 后续可接 GitHub、Filesystem、Browser、数据库等 MCP 能力 |
| RAG | `plugins/rag/base.py` 预留 | 后续可接 Markdown、PDF、TXT、知识库索引 |
| 多 Agent | `agents/base.py` 预留 | 后续可实现任务分解、专家 Agent、工作流编排 |
| QQ 通知管理命令 | 文档规划中 | 可新增 `/notify status/off/quiet/normal/verbose/mute/history` |
| 内部 Hook API | 文档规划中 | 可新增 `POST /internal/claude-hook`，Hook 只转发事件 |
| 通知历史 | 文档规划中 | 可新增 `data/notify-history.jsonl` 供查询与审计 |
| 工作区持久化 | Docker Compose 当前未挂载 `/workspace` | 生产建议增加 `./workspace:/workspace` |

## 23. 标签

#agent-qq #SOP #NapCat #OneBot #ClaudeCode #ClaudeCLI #QQBot #DockerCompose #systemd #Hook #QQ通知 #防轰炸 #运维 #故障排查 #安全检查
