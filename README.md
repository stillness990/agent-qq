# agent-qq

`agent-qq` 是一个基于 NapCat QQ、OneBot v11、Python Gateway 和 Claude Code CLI 的 QQ AI Agent 系统。

## 架构

```text
QQ
→ NapCat QQ
→ OneBot v11
→ Python Gateway（纯指令驱动）
→ Claude Code CLI（仅 /plan 触发）
→ 已在 Claude Code 中配置的模型
→ 返回结果到 QQ
```

**核心原则：仅 `/plan <自然语言>` 能与 AI 交互，其余所有命令均为纯脚本/子进程执行，零 AI Token 消耗。**

业务层不直接调用 Claude API，也不需要在 Python 代码里配置 Anthropic SDK。所有智能能力通过本机 `claude` CLI 完成。

## 功能

- 支持 NapCat QQ / OneBot v11 WebSocket
- 支持 QQ 私聊
- 纯指令驱动架构：14 条命令，仅 `/plan` 触发 AI
- 支持 Plan 状态机（/plan → /plan-status → /plan-start /plan-cancel → /plan-log）
- 支持后台任务监控（5s 轮询巡检）
- 支持异常熔断（Token 耗尽 / 网络异常 / 任务超时三路检测）
- 支持日志轮转（条数限制 + 终态自动清理）
- 支持自动重连
- 支持消息去重
- 支持 Docker Compose 部署
- 所有配置集中在 `.env`
- 支持 Claude Code Hook QQ 通知，通知程序在项目内独立运行
- 预留 MCP、RAG、多 Agent 扩展接口

## 快速开始

### 1. 复制配置

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
nano .env
```

至少修改：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ADMIN_QQ_IDS=<ADMIN_QQ_ID>
CLAUDE_CONFIG_DIR=/path/to/.claude
```

### 2. 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 3. Docker Compose 部署

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f agent-qq
```

### 4. systemd 服务部署

```bash
sudo bash deploy/register-agent-qq-service.sh
```

## NapCat / OneBot 配置

在 NapCat 中启用 OneBot v11 WebSocket 服务，例如：

```text
监听地址：0.0.0.0
监听端口：3001
access_token：可选
```

如果 agent-qq 运行在 Docker 容器里，`.env` 中通常使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

如果 agent-qq 和 NapCat 在同一个 Docker 网络中，可以改成服务名地址。

## QQ 命令

### 通用命令（零 Token 消耗）

```text
/help          查看完整命令列表
/ping          延迟检测 + 在线状态
/network       网络质量测试（优/良/差）
/status        查看运行中任务
/stop <id>     按 ID 停止任务
/kill <id>     /stop 别名
/clear         重置上下文
/token         查询 Token 信息
/weather       天气推送
/log           查看日志
```

### AI 交互（唯一入口）

```text
/plan <描述>       生成执行大纲（不执行，仅返回计划）
/plan-status       查看待确认计划
/plan-start        确认并执行计划
/plan-cancel       取消待确认计划
/plan-log          查看计划历史
```

### 管理员命令

```text
/shell <command>   执行白名单 shell 命令（仅管理员）
```

安全策略：

- `/shell` 默认只允许管理员使用
- `/shell` 默认只允许白名单命令前缀
- `/plan` 仅返回 AI 大纲，需 `/plan-start` 确认后才执行
- 非命令文本返回 `/help` 提示，不会透传给 AI
- 同一时间仅允许 1 个待确认计划

## Claude Code CLI

宿主机需先完成 Claude Code 登录和模型配置：

```bash
claude --version
claude -p "你好"
```

Docker 部署时，项目会把宿主机 Claude 配置目录挂载到容器：

```yaml
${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

## 项目结构

```text
agent-qq/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── bot.py                  # 主入口
├── config.py               # 配置管理（Pydantic Settings）
├── qq_client.py            # OneBot v11 WebSocket 客户端
├── claude_client.py        # Claude Code CLI 调用封装
├── command_router.py       # 指令路由（14 条命令）
├── plan_state.py           # Plan 状态机
├── task_registry.py        # 任务注册表
├── task_status_log.py      # 任务状态持久化日志
├── task_monitor.py         # 后台任务监控
├── circuit_breaker.py      # 异常熔断器
├── log_rotator.py          # 日志轮转
├── plugins/
│   ├── mcp/
│   └── rag/
├── agents/
├── notifications/          # Claude Code QQ 通知系统
├── scripts/                # 工具脚本
├── tests/                  # 测试用例（53 个）
├── deploy/                 # 部署配置（systemd）
└── README.md
```

## 测试

```bash
.venv/bin/python -m pytest -q
```

如果当前环境没有安装依赖，可先做语法检查：

```bash
python3 -m compileall .
```

## OneBot 推送测试

先确认 NapCat 已启用 OneBot v11 WebSocket，然后检查连接：

```bash
.venv/bin/python scripts/check_onebot.py --url ws://127.0.0.1:3001
```

向指定 QQ 发送一条私聊测试消息：

```bash
.venv/bin/python scripts/send_test_private_msg.py --to <ADMIN_QQ_ID> --message "agent-qq 测试消息"
```

如果 NapCat 配置了 access_token，需要加上：

```bash
.venv/bin/python scripts/send_test_private_msg.py --to <ADMIN_QQ_ID> --token <ONEBOT_ACCESS_TOKEN>
```

## Claude Code Hook QQ 通知

`agent-qq` 已内置 Claude Code QQ 通知系统，代码位于：

```text
notifications/
scripts/claude_notify_hook.py
```

该通知程序可以由 Claude Code Hook 独立调用，不依赖 `bot.py` 主进程在线；只要 NapCat / OneBot v11 WebSocket 可用，就能向管理员 QQ 发送任务开始、阶段变化、失败、长任务心跳和本轮完成汇总。

通知配置集中在 `.env`，样例见 `.env.example`。部署时请按实际 OneBot 地址、管理员 QQ 和 Claude Code 配置目录填写本地 `.env`；不要提交 `.env`、Claude 配置目录、日志或运行状态文件。

## 异常熔断

v2.0 内置三路熔断检测：

| 通道 | 检测方式 | 阈值 |
|------|---------|------|
| Token 耗尽 | Claude 返回值关键词匹配（10 个模式） | 1 次触发 |
| 网络异常 | 连续连接错误计数 | 3 次连续 |
| 任务超时 | 运行时长 vs 阈值 | 30 分钟 |

熔断后自动终止任务、QQ 通知管理员、状态标记 EXCEPTION。

## 后续扩展

- `/search`：接入搜索工具
- `/agent`：接入多 Agent 调度
- `/mcp`：接入 MCP Filesystem / GitHub / Browser / PostgreSQL / MySQL
- `/rag`：接入 Markdown / PDF / TXT / 企业知识库
- `/workflow`：接入工作流编排
