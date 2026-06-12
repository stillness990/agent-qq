# agent-qq

`agent-qq` 是一个基于 NapCat QQ、OneBot v11、Python Gateway 和 Claude Code CLI 的 QQ AI Agent 系统。

## 架构

```text
QQ
→ NapCat QQ
→ OneBot v11
→ Python Gateway
→ Claude Code CLI
→ 已在 Claude Code 中配置的模型
→ 返回结果到 QQ
```

业务层不直接调用 Claude API，也不需要在 Python 代码里配置 Anthropic SDK。所有智能能力通过本机 `claude` CLI 完成。

## 功能

- 支持 NapCat QQ / OneBot v11 WebSocket
- 支持 QQ 私聊
- 支持 `/help`、`/status`、`/ask`、`/log`、`/shell`、`/code`
- 支持自动重连
- 支持消息去重
- 支持错误日志
- 支持 Docker Compose 部署
- 所有配置集中在 `.env`
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
ADMIN_QQ_IDS=你的QQ号
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

```text
/help
/status
/ask 你好
/log
/shell pwd
/code 创建一个 Python 脚本
```

安全策略：

- `/shell` 默认只允许管理员使用；
- `/shell` 默认只允许白名单命令前缀；
- `/code` 默认只允许管理员使用；
- 普通私聊文本会作为问题交给 Claude Code CLI。

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
├── bot.py
├── config.py
├── qq_client.py
├── claude_client.py
├── command_router.py
├── plugins/
│   ├── mcp/
│   └── rag/
├── agents/
├── blog/
├── logs/
├── tests/
└── README.md
```

## 测试

本机没有 `python3-pip` / `ensurepip` 时，可以使用已安装的 `uv` 创建测试环境：

```bash
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
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
.venv/bin/python scripts/send_test_private_msg.py --to 你的QQ号 --message "agent-qq 测试消息"
```

如果 NapCat 配置了 access_token，需要加上：

```bash
.venv/bin/python scripts/send_test_private_msg.py --to 你的QQ号 --token 你的token
```

## 后续扩展

- `/search`：接入搜索工具
- `/agent`：接入多 Agent 调度
- `/mcp`：接入 MCP Filesystem / GitHub / Browser / PostgreSQL / MySQL
- `/rag`：接入 Markdown / PDF / TXT / 企业知识库
- `/workflow`：接入工作流编排
