# agent-qq 完整安装部署流程

本文档由现有安装、Docker、NapCat、OneBot、Claude Code、FAQ、架构与接口说明合并整理而成，目标是形成一份可以直接按步骤实施的安装部署文档。

## 1. 项目概述

agent-qq 是一个通过 QQ 私聊接入 Claude Code CLI 的机器人网关。它本身不直接调用 Claude API，也不依赖 Anthropic SDK，而是通过本机或容器内的 `claude` 命令执行智能任务。

整体链路如下：

```text
QQ
→ NapCat QQ
→ OneBot v11 WebSocket
→ Python Gateway(agent-qq)
→ Claude Code CLI
→ 本机 Claude Code 配置中的模型
→ 返回结果到 QQ
```

核心设计原则：

1. Python 业务层不直接调用 Claude API。
2. 智能能力统一通过 Claude Code CLI 执行。
3. 不在 `.env` 或 Python 业务代码中保存 Anthropic API Key。
4. 不在业务层硬编码模型，模型选择由 Claude Code CLI 本机配置决定。
5. 高风险能力默认仅管理员可用。
6. OneBot WebSocket 连接具备自动重连能力。
7. 消息处理异步执行，避免阻塞 WebSocket 接收。

## 2. 部署前准备

### 2.1 基础环境

建议环境：

- Ubuntu 24.04 或其他 Linux 服务器
- Python 3.12
- Docker 与 Docker Compose
- Git
- Node.js/npm，容器内安装 Claude Code CLI 时需要
- NapCat QQ
- 已登录并配置完成的 Claude Code CLI

### 2.2 组件职责

| 组件 | 作用 |
|---|---|
| QQ | 用户通过私聊发送命令 |
| NapCat QQ | 登录机器人 QQ，并提供 OneBot v11 WebSocket 服务 |
| OneBot v11 | QQ 与 agent-qq 之间的协议层 |
| agent-qq | Python Gateway，负责连接、命令解析、权限控制、调用 Claude Code |
| Claude Code CLI | 实际执行 `/ask`、`/code` 等智能任务 |
| Docker Compose | 可选，用于容器化部署 agent-qq |

## 3. 获取项目

如果项目在 GitHub 上：

```bash
git clone https://github.com/<your-github-user>/agent-qq.git
cd agent-qq
```

如果已经是本地目录，直接进入项目根目录：

```bash
cd /path/to/agent-qq
```

后续所有命令默认都在项目根目录执行。

## 4. 配置 NapCat QQ

### 4.1 安装并登录 NapCat QQ

按 NapCat 官方文档安装 NapCat QQ，并使用机器人 QQ 账号登录。

### 4.2 启用 OneBot v11 WebSocket

在 NapCat 配置中启用 OneBot v11 WebSocket 服务。

推荐配置：

```text
Host: 0.0.0.0
Port: 3001
Access Token: 可选
```

说明：

- `Host=0.0.0.0` 便于 Docker 容器访问宿主机上的 NapCat。
- `Port=3001` 是本文档统一使用的示例端口。
- 如果配置了 `Access Token`，agent-qq 的 `.env` 中必须同步填写同一个 token。

## 5. 配置 OneBot 连接

agent-qq 通过 WebSocket 连接 NapCat 提供的 OneBot v11 服务。

### 5.1 宿主机运行 agent-qq

如果 agent-qq 直接在宿主机运行，`.env` 中使用：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

### 5.2 Docker 容器运行 agent-qq

如果 agent-qq 在 Docker 容器中运行，容器访问宿主机 NapCat 通常使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

### 5.3 Access Token

如果 NapCat OneBot 配置中设置了 access token，`.env` 中同步填写：

```env
ONEBOT_ACCESS_TOKEN=你的token
```

如果 NapCat 未设置 token，可以留空：

```env
ONEBOT_ACCESS_TOKEN=
```

### 5.4 当前支持的 OneBot 能力

当前版本处理的事件：

- `post_type=message`
- `message_type=private`

即仅处理 QQ 私聊消息。

当前版本调用的动作：

- `send_private_msg`

用于向用户发送 QQ 私聊回复。

OneBot 文本消息示例：

```json
{
  "type": "text",
  "data": {
    "text": "/ask 你好"
  }
}
```

## 6. 准备 Claude Code CLI

### 6.1 宿主机检查

在宿主机执行：

```bash
claude --version
claude -p "你好"
```

如果能正常输出版本号并返回回答，说明宿主机 Claude Code CLI 可用。

### 6.2 Claude Code 相关配置项

`.env` 中建议配置：

```env
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
CLAUDE_CONFIG_DIR=/path/to/.claude
```

字段说明：

| 配置项 | 示例 | 说明 |
|---|---|---|
| `CLAUDE_CLI_COMMAND` | `claude` | agent-qq 调用的 Claude Code CLI 命令 |
| `CLAUDE_TIMEOUT_SECONDS` | `180` | 单次 Claude 调用超时时间，单位秒 |
| `CLAUDE_WORKDIR` | `/workspace` | Claude Code 执行任务时的工作目录 |
| `CLAUDE_CONFIG_DIR` | `/home/your-user/.claude` | 宿主机 Claude Code 配置目录，Docker 部署时会挂载到容器 |

### 6.3 Docker 内使用 Claude Code CLI

Dockerfile 中需要安装 Claude Code CLI：

```dockerfile
RUN npm install -g @anthropic-ai/claude-code
```

Docker Compose 中需要挂载宿主机 Claude Code 配置：

```yaml
${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

该挂载建议保持只读 `:ro`，避免容器修改宿主机 Claude Code 配置。

### 6.4 安全边界

- 不在 Python 业务层保存 Claude API Key。
- 不在 `.env` 中配置 Anthropic API Key。
- 不从业务层选择或硬编码模型。
- 模型、账号、认证状态由宿主机 Claude Code CLI 配置决定。
- Docker 部署时仅挂载 Claude Code 配置目录，不额外写入密钥。

## 7. 配置 agent-qq 环境变量

复制环境变量模板：

```bash
cp .env.example .env
nano .env
```

如果项目中没有 `.env.example`，可以手动创建 `.env`，按下面内容填写。

### 7.1 Docker 部署推荐配置

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ONEBOT_ACCESS_TOKEN=
ADMIN_QQ_IDS=你的QQ号

CLAUDE_CONFIG_DIR=/home/your-user/.claude
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace

SHELL_ALLOWED_PREFIXES=pwd,ls,git status
```

### 7.2 宿主机本地运行推荐配置

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
ONEBOT_ACCESS_TOKEN=
ADMIN_QQ_IDS=你的QQ号

CLAUDE_CONFIG_DIR=/home/your-user/.claude
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/path/to/agent-qq

SHELL_ALLOWED_PREFIXES=pwd,ls,git status
```

### 7.3 关键变量说明

| 配置项 | 是否必填 | 说明 |
|---|---:|---|
| `ONEBOT_WS_URL` | 是 | NapCat OneBot v11 WebSocket 地址 |
| `ONEBOT_ACCESS_TOKEN` | 否 | NapCat 配置了 token 时必填，否则留空 |
| `ADMIN_QQ_IDS` | 建议填写 | 管理员 QQ 号，多个可按项目支持的格式填写 |
| `CLAUDE_CONFIG_DIR` | Docker 部署必填 | 宿主机 Claude Code 配置目录 |
| `CLAUDE_CLI_COMMAND` | 建议填写 | Claude Code CLI 命令，通常为 `claude` |
| `CLAUDE_TIMEOUT_SECONDS` | 建议填写 | Claude Code 调用超时时间 |
| `CLAUDE_WORKDIR` | 建议填写 | Claude Code 执行任务的工作目录 |
| `SHELL_ALLOWED_PREFIXES` | 使用 `/shell` 时需要 | `/shell` 命令允许执行的命令前缀白名单 |

## 8. 本地运行流程

适合开发调试或不希望使用 Docker 的场景。

### 8.1 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 8.2 确认本地 OneBot 地址

本地运行时，`.env` 中一般配置：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

### 8.3 启动服务

```bash
python bot.py
```

启动后观察控制台日志，确认已连接到 NapCat OneBot WebSocket。

### 8.4 本地运行检查点

依次确认：

1. NapCat QQ 已登录。
2. NapCat OneBot v11 WebSocket 已启动。
3. `.env` 中的 `ONEBOT_WS_URL` 端口与 NapCat 端口一致。
4. 宿主机执行 `claude -p "你好"` 正常。
5. `ADMIN_QQ_IDS` 已配置为你的 QQ 号。
6. 向机器人 QQ 私聊 `/status` 能收到回复。

## 9. Docker 部署流程

适合服务器长期运行。

### 9.1 确认 Docker Compose 配置

Docker Compose 需要包含以下关键能力：

1. 构建并运行 agent-qq 容器。
2. 挂载宿主机 Claude Code 配置目录到容器内 `/root/.claude:ro`。
3. 让容器能够访问宿主机 NapCat 的 `3001` 端口。

Claude Code 配置挂载示例：

```yaml
${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

### 9.2 构建镜像

```bash
docker compose build
```

### 9.3 启动服务

```bash
docker compose up -d
```

也可以一条命令构建并启动：

```bash
docker compose up -d --build
```

### 9.4 查看服务状态

```bash
docker compose ps
```

### 9.5 查看日志

```bash
docker compose logs -f agent-qq
```

也可以查看项目日志文件：

```text
logs/agent-qq.log
```

### 9.6 重启服务

```bash
docker compose restart agent-qq
```

### 9.7 停止服务

```bash
docker compose down
```

### 9.8 更新代码后重建

```bash
git pull
docker compose up -d --build
```

重建完成后查看日志：

```bash
docker compose logs -f agent-qq
```

## 10. 部署后验证

### 10.1 检查容器状态

```bash
docker compose ps
```

确认 `agent-qq` 服务处于运行状态。

### 10.2 检查日志

```bash
docker compose logs -f agent-qq
```

重点确认：

- 已读取 `.env` 配置。
- 已连接 OneBot WebSocket。
- 没有 Claude CLI 调用失败错误。
- 没有权限或配置目录挂载错误。

### 10.3 QQ 私聊测试

向机器人 QQ 私聊发送：

```text
/help
```

预期：返回可用命令帮助。

继续发送：

```text
/status
```

预期：返回运行状态，说明 QQ → NapCat → OneBot → agent-qq 链路正常。

继续发送：

```text
/ask 你好
```

预期：返回 Claude Code 生成的回答，说明 agent-qq → Claude Code CLI 链路正常。

## 11. 支持的 QQ 命令

| 命令 | 权限 | 说明 |
|---|---|---|
| `/help` | 所有人 | 查看帮助 |
| `/status` | 所有人 | 查看运行状态 |
| `/ask 文本` | 所有人 | 调用 Claude Code 回答问题 |
| `/log` | 管理员 | 查看日志位置 |
| `/shell 命令` | 管理员 | 执行白名单 Shell 命令 |
| `/code 需求` | 管理员 | 调用 Claude Code 执行代码任务 |

预留命令：

- `/search`
- `/agent`
- `/mcp`
- `/rag`
- `/workflow`

## 12. 安全与权限

### 12.1 管理员 QQ

将自己的 QQ 号配置到：

```env
ADMIN_QQ_IDS=你的QQ号
```

管理员命令包括但不限于：

- `/log`
- `/shell`
- `/code`

### 12.2 `/shell` 白名单

为了安全，`/shell` 仅允许管理员使用，并且只允许执行白名单命令前缀。

示例：

```env
SHELL_ALLOWED_PREFIXES=pwd,ls,git status
```

表示仅允许执行以 `pwd`、`ls`、`git status` 开头的命令。

生产环境建议：

- 不要将 `rm`、`curl`、`wget`、`ssh`、`scp`、`bash`、`sh` 等高风险命令加入白名单。
- 不要给普通用户开放 `/shell`。
- 管理员 QQ 号应只配置可信账号。

### 12.3 Claude Code 配置安全

Docker 部署时建议只读挂载：

```yaml
/root/.claude:ro
```

避免容器内程序修改宿主机 Claude Code 配置。

### 12.4 Git 推送安全

如果需要发布代码，可按以下流程：

```bash
git add .
git commit -m "chore: update agent-qq"
git push
```

生产环境不建议完全无确认自动推送高风险代码，至少保留测试通过后再推送的步骤。

## 13. 故障排查

### 13.1 OneBot 404 或连接失败

检查项：

1. NapCat QQ 是否已启动并登录。
2. OneBot v11 WebSocket 是否已启用。
3. NapCat 端口是否为 `3001`。
4. `.env` 中 `ONEBOT_WS_URL` 是否正确。

宿主机运行时：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

Docker 运行时：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

### 13.2 Docker 容器无法连接宿主机 NapCat

检查项：

1. NapCat OneBot 的 Host 是否为 `0.0.0.0`。
2. 端口是否开放。
3. `.env` 是否使用 `ws://host.docker.internal:3001`。
4. 如果当前 Linux Docker 环境不支持 `host.docker.internal`，需要在 `docker-compose.yml` 中增加对应 host 映射，或改用宿主机网关地址。

### 13.3 `/status` 没有回复

检查项：

1. 查看 agent-qq 日志。
2. 确认机器人 QQ 与发送消息的 QQ 是私聊关系。
3. 确认当前版本只处理私聊消息，不处理群聊消息。
4. 确认 OneBot 收到了 `message_type=private` 事件。

### 13.4 `/ask` 没有回复或超时

检查项：

1. 宿主机执行：

   ```bash
   claude -p "你好"
   ```

2. Docker 部署时确认容器内安装了 Claude Code CLI。
3. 确认 `.claude` 配置目录已正确挂载到容器。
4. 适当增大：

   ```env
   CLAUDE_TIMEOUT_SECONDS=180
   ```

### 13.5 Docker 里为什么也需要 Claude Code CLI

容器内运行 Python Gateway 时，agent-qq 需要能执行 `claude -p` 命令，因此 Dockerfile 需要安装 Claude Code CLI，并通过 Docker Compose 挂载宿主机 `.claude` 配置。

### 13.6 `/shell` 不能执行某些命令

这是安全限制。`/shell` 只允许管理员使用，并且命令必须匹配白名单前缀。

修改示例：

```env
SHELL_ALLOWED_PREFIXES=pwd,ls,git status
```

修改后重启服务：

```bash
docker compose restart agent-qq
```

### 13.7 如何查看日志

Docker 日志：

```bash
docker compose logs -f agent-qq
```

项目日志文件：

```text
logs/agent-qq.log
```

## 14. 模块说明

| 模块 | 说明 |
|---|---|
| `bot.py` | 主程序，负责连接、重连、事件循环和异步消息处理 |
| `config.py` | 读取 `.env` 配置 |
| `qq_client.py` | OneBot v11 WebSocket 客户端 |
| `claude_client.py` | Claude Code CLI 调用封装 |
| `command_router.py` | QQ 命令解析和路由 |
| `plugins/mcp/` | MCP 预留接口 |
| `plugins/rag/` | RAG 预留接口 |
| `agents/` | 多 Agent 预留接口 |
| `tests/` | 测试用例 |

## 15. 从零复现标准流程

本节按“全新机器 + 已安装 NapCat/QQ + 已有 Claude Code 账号”的视角描述完整复现路径。前面的章节解释原因，本节给出可以照抄执行的顺序。

### 15.1 复现前确认信息

开始前先确认以下信息，后续配置会用到：

| 信息 | 示例 | 获取方式 |
|---|---|---|
| 机器人 QQ 号 | `<bot_qq_id>` | 用于登录 NapCat QQ |
| 管理员 QQ 号 | `<admin_qq_id>` | 你的个人 QQ，用于接收 `/code`、`/shell` 等管理员能力 |
| OneBot WebSocket 地址 | `ws://127.0.0.1:3001` 或 `ws://host.docker.internal:3001` | NapCat WebUI 的 OneBot v11 WebSocket Server 配置 |
| OneBot access token | 可为空 | NapCat OneBot 配置中如填写 token，这里必须一致 |
| Claude Code 配置目录 | `/home/ww/.claude` | 宿主机上执行 `claude` 后生成的配置目录 |
| agent-qq 工作目录 | `/workspace` 或项目目录 | Claude Code 执行任务时所在目录 |

> 说明：`ADMIN_QQ_IDS` 配置的是“允许使用管理员命令的发送方 QQ”，不是机器人 QQ。

### 15.2 第一步：配置并验证 NapCat

1. 启动 NapCat QQ，并用机器人 QQ 号完成登录。
2. 打开 NapCat WebUI，启用 OneBot v11 WebSocket Server。
3. 推荐配置如下：

   ```text
   Host: 0.0.0.0
   Port: 3001
   Access Token: 可先留空；生产环境建议填写随机长字符串
   ```

4. 保存后确认端口监听：

   ```bash
   ss -ltn | grep 3001
   ```

   预期能看到 `3001` 处于监听状态。

5. 如果使用 Docker 部署 agent-qq，NapCat 的 Host 不建议只绑定 `127.0.0.1`，否则容器可能无法访问宿主机端口。

### 15.3 第二步：配置并验证 Claude Code CLI

在宿主机执行：

```bash
claude --version
claude -p "你好，请只回复 OK"
```

预期：

- 第一条命令能输出 Claude Code 版本。
- 第二条命令能正常返回内容。

如果没有登录，请先在宿主机完成 Claude Code 登录和模型配置。agent-qq 只调用 `claude -p`，不会在 Python 代码里读取 Anthropic API Key，也不会直接选择模型。

### 15.4 第三步：准备项目目录

```bash
git clone https://github.com/<your-github-user>/agent-qq.git
cd agent-qq
cp .env.example .env
mkdir -p logs workspace
```

`logs` 很重要：本地直接运行 `python bot.py` 时，程序会写入 `logs/agent-qq.log`。如果目录不存在，日志文件初始化可能失败。

### 15.5 第四步：填写 `.env`

#### Docker 部署推荐 `.env`

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ONEBOT_ACCESS_TOKEN=
ENABLE_PRIVATE_CHAT=true
ADMIN_QQ_IDS=你的管理员QQ号

CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
CLAUDE_CONFIG_DIR=/home/your-user/.claude

ENABLE_SHELL_COMMAND=true
SHELL_ALLOWED_PREFIXES=pwd,ls,git status,python --version,python3 --version,df -h,free -h,whoami,uname -a

MESSAGE_DEDUPE_TTL_SECONDS=300
LOG_LEVEL=INFO
RECONNECT_INITIAL_SECONDS=2
RECONNECT_MAX_SECONDS=60
QQ_REPLY_CHUNK_SIZE=1800
```

#### 宿主机本地运行推荐 `.env`

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
ONEBOT_ACCESS_TOKEN=
ENABLE_PRIVATE_CHAT=true
ADMIN_QQ_IDS=你的管理员QQ号

CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/path/to/agent-qq/workspace
CLAUDE_CONFIG_DIR=/home/your-user/.claude

ENABLE_SHELL_COMMAND=true
SHELL_ALLOWED_PREFIXES=pwd,ls,git status,python --version,python3 --version,df -h,free -h,whoami,uname -a

MESSAGE_DEDUPE_TTL_SECONDS=300
LOG_LEVEL=INFO
RECONNECT_INITIAL_SECONDS=2
RECONNECT_MAX_SECONDS=60
QQ_REPLY_CHUNK_SIZE=1800
```

变量细节：

| 变量 | 默认值 | 是否必须 | 说明 |
|---|---|---:|---|
| `ONEBOT_WS_URL` | `ws://127.0.0.1:3001` | 是 | OneBot v11 WebSocket 地址。Docker 容器访问宿主机通常用 `host.docker.internal`。 |
| `ONEBOT_ACCESS_TOKEN` | 空 | 否 | 如果 NapCat 配置了 token，程序会以 `Authorization: Bearer <token>` 连接。 |
| `ENABLE_PRIVATE_CHAT` | `true` | 否 | 当前版本只处理私聊；设为 `false` 后不会响应私聊。 |
| `ADMIN_QQ_IDS` | 空集合 | 强烈建议 | 多个 QQ 号用英文逗号分隔，例如 `111,222`。 |
| `CLAUDE_CLI_COMMAND` | `claude` | 否 | Claude Code CLI 命令名；如果不在 PATH，可填绝对路径。 |
| `CLAUDE_TIMEOUT_SECONDS` | `180` | 否 | `/ask`、`/code`、`/shell` 等命令的超时时间。 |
| `CLAUDE_WORKDIR` | `/workspace` | 否 | Claude Code 和 `/shell` 执行目录；程序会自动创建该目录。 |
| `CLAUDE_CONFIG_DIR` | 无代码默认值 | Docker 必填 | `docker-compose.yml` 用它把宿主机 `.claude` 挂载到容器 `/root/.claude:ro`。 |
| `ENABLE_SHELL_COMMAND` | `false` | 否 | 是否启用 `/shell`；`.env.example` 为演示设置成 `true`，生产按需开启。 |
| `SHELL_ALLOWED_PREFIXES` | `pwd,ls` | 使用 `/shell` 时必填 | `/shell` 白名单前缀，多个用英文逗号分隔。 |
| `MESSAGE_DEDUPE_TTL_SECONDS` | `300` | 否 | 消息去重时间窗口，避免 OneBot 重推导致重复执行。 |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`。 |
| `RECONNECT_INITIAL_SECONDS` | `2` | 否 | OneBot 断线后首次重连等待秒数。 |
| `RECONNECT_MAX_SECONDS` | `60` | 否 | OneBot 指数退避重连最大等待秒数。 |
| `QQ_REPLY_CHUNK_SIZE` | `1800` | 否 | QQ 单条回复分段长度，长回答会分多条私聊发送。 |

### 15.6 第五步：先做链路预检

安装依赖后可以先检查 OneBot 连接，不必启动完整机器人：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/check_onebot.py
```

如果 `.env` 中的地址不是当前要测的地址，可以覆盖：

```bash
python scripts/check_onebot.py --url ws://127.0.0.1:3001
python scripts/check_onebot.py --url ws://127.0.0.1:3001 --token 你的token
```

预期输出：

```text
ok: connected to ws://127.0.0.1:3001
```

还可以让机器人 QQ 主动给管理员 QQ 发一条测试私聊：

```bash
python scripts/send_test_private_msg.py --to 你的管理员QQ号 --message "agent-qq OneBot 推送测试"
```

如果 NapCat 配置了 token：

```bash
python scripts/send_test_private_msg.py --to 你的管理员QQ号 --token 你的token
```

### 15.7 第六步：选择一种启动方式

#### 方式 A：本地前台运行，适合调试

```bash
source .venv/bin/activate
python bot.py
```

看到类似日志即表示连接成功：

```text
Connected to OneBot: ws://127.0.0.1:3001
```

#### 方式 B：本地脚本启动，适合桌面环境

项目提供 `scripts/start_agent_qq.sh`，会尝试启动 NapCat，等待 WebUI 和 OneBot 端口，再启动 bot：

```bash
chmod +x scripts/start_agent_qq.sh
scripts/start_agent_qq.sh background
```

前台运行：

```bash
scripts/start_agent_qq.sh --foreground
```

可覆盖的常用变量：

```bash
PYTHON_BIN=/path/to/agent-qq/.venv/bin/python \
NAPCAT_LAUNCHER=$HOME/.local/bin/napcat-qq \
ONEBOT_PORT=3001 \
WEBUI_PORT=6099 \
WAIT_SECONDS=180 \
scripts/start_agent_qq.sh background
```

脚本日志：

```text
logs/napcat.stdout.log
logs/agent-qq.stdout.log
logs/agent-qq.log
```

#### 方式 C：Docker Compose 运行，适合服务器长期部署

```bash
docker compose up -d --build
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f agent-qq
```

当前 `docker-compose.yml` 已包含：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
volumes:
  - ./logs:/app/logs
  - ./plugins:/app/plugins
  - ./agents:/app/agents
  - ${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

如果希望容器内 `/workspace` 的 Claude Code 工作区持久化，建议额外增加：

```yaml
volumes:
  - ./workspace:/workspace
```

否则 `/workspace` 会在容器文件系统内自动创建，重建容器后其中内容可能丢失。

### 15.8 第七步：QQ 端验证

用管理员 QQ 私聊机器人 QQ，依次发送：

```text
/help
```

预期返回命令列表。

```text
/status
```

预期返回：

- `agent-qq 正常运行`
- 当前用户是否管理员
- 私聊支持状态
- Shell 命令启用状态
- Claude Code CLI 检查结果

继续测试 Claude 链路：

```text
/ask 你好，请只回复 OK
```

预期返回 Claude Code CLI 生成的回答。

如果配置了管理员 QQ，可以继续测试管理员命令：

```text
/log
/shell pwd
/code 请生成一个最小 Python hello world 示例，只需要给代码块
```

注意：普通私聊文本如果不带命令，也会被当作问题交给 Claude Code CLI。

### 15.9 复现成功判定

满足以下条件即可认为部署复现成功：

1. NapCat QQ 登录在线。
2. OneBot v11 WebSocket 端口可连接。
3. `scripts/check_onebot.py` 输出 `ok`。
4. `claude -p "你好"` 在宿主机可正常执行。
5. agent-qq 日志出现 `Connected to OneBot`。
6. QQ 私聊 `/help` 能返回命令帮助。
7. QQ 私聊 `/status` 能显示 Claude Code CLI 可用。
8. QQ 私聊 `/ask 你好` 能返回模型回答。

## 16. 发布前脱敏与仓库上传流程

将项目发布到公开或半公开仓库前，必须先在副本中脱敏，不要直接把运行目录原样推送。

### 16.1 必须排除的本地运行文件

以下文件或目录不应进入发布仓库：

```text
.env
.venv/
__pycache__/
.pytest_cache/
logs/*.log
logs/*.log.*
guild1.db*
napcat_*.json
.claude/settings.local.json
```

说明：

- `.env` 可能包含 OneBot token、管理员 QQ 号、真实路径。
- `guild1.db*` 是 NapCat/QQ 运行数据库，可能包含账号、群、联系人或消息相关数据。
- `logs/` 可能包含 QQ 号、消息内容、错误堆栈和本机路径。
- `.claude/settings.local.json` 是本机 Claude Code 的本地设置，不应发布。
- `.venv/`、`__pycache__/`、`.pytest_cache/` 是构建/缓存产物，不应发布。

### 16.2 推荐复制命令

复制到发布目录时建议使用 `rsync` 排除敏感和缓存文件：

```bash
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude 'logs/*.log' \
  --exclude 'logs/*.log.*' \
  --exclude 'guild1.db*' \
  --exclude 'napcat_*.json' \
  --exclude '.claude/settings.local.json' \
  ./ /media/ww/d1f01292-c940-497e-8051-a0b76acd008c/agent-qq/
```

如果目标目录本身就是 Git 仓库，复制完成后在目标目录执行检查：

```bash
git status --short
git diff -- . ':!*.log'
```

### 16.3 脱敏检查命令

发布前建议至少检查这些模式：

```bash
rg -n "(sk-ant|ANTHROPIC_API_KEY|access_token|ONEBOT_ACCESS_TOKEN|ADMIN_QQ_IDS|password|secret|token|Bearer|[0-9]{6,})" . -S --glob '!agent-qq完整安装部署流程.md'
find . -name '__pycache__' -o -name '*.pyc' -o -name '.env' -o -name 'guild1.db*'
```

命中不一定都是敏感信息，例如源码中的变量名或文档里的占位符可以保留；但真实 token、真实 QQ 号、真实路径、日志和数据库必须移除或改成占位符。

### 16.4 发布前验证

在脱敏后的目录中执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

如果只验证 Docker 构建：

```bash
docker compose build
```

最后再提交和推送：

```bash
git add .
git commit -m "chore: publish sanitized agent-qq"
git push
```

## 17. 重要实现细节

### 17.1 消息处理与去重

`bot.py` 接收 OneBot 事件后会异步创建处理任务，避免一个 Claude Code 请求阻塞后续 WebSocket 消息接收。消息去重键为：

```text
<message_type>:<user_id>:<message_id>
```

`MESSAGE_DEDUPE_TTL_SECONDS` 控制去重缓存时间，默认 300 秒。

### 17.2 OneBot 鉴权方式

如果配置了 `ONEBOT_ACCESS_TOKEN`，WebSocket 连接时会使用：

```http
Authorization: Bearer <ONEBOT_ACCESS_TOKEN>
```

因此 NapCat 侧 token 和 `.env` 必须完全一致。

### 17.3 Claude Code 调用方式

`claude_client.py` 会构造：

```bash
claude -p '<用户问题或封装后的代码任务提示>'
```

- `/ask` 直接传入用户问题。
- 普通私聊文本等同于 `/ask`。
- `/code` 会额外加上“谨慎代码助手”的提示，且仅管理员可用。
- 超时由 `CLAUDE_TIMEOUT_SECONDS` 控制。
- 执行目录由 `CLAUDE_WORKDIR` 控制。

### 17.4 日志位置

| 运行方式 | 日志位置 |
|---|---|
| Python 前台运行 | 控制台 + `logs/agent-qq.log` |
| `start_agent_qq.sh background` | `logs/agent-qq.stdout.log` + `logs/agent-qq.log` |
| Docker Compose | `docker compose logs -f agent-qq` + `logs/agent-qq.log` |

## 18. 最小可执行部署清单

如果只需要快速部署，按以下顺序执行：

1. 安装并登录 NapCat QQ。
2. 在 NapCat 中启用 OneBot v11 WebSocket：

   ```text
   Host: 0.0.0.0
   Port: 3001
   ```

3. 确认宿主机 Claude Code CLI 可用：

   ```bash
   claude --version
   claude -p "你好"
   ```

4. 获取项目并进入目录：

   ```bash
   git clone https://github.com/<your-github-user>/agent-qq.git
   cd agent-qq
   ```

5. 创建 `.env`：

   ```bash
   cp .env.example .env
   nano .env
   ```

6. Docker 部署时填写：

   ```env
   ONEBOT_WS_URL=ws://host.docker.internal:3001
   ONEBOT_ACCESS_TOKEN=
   ADMIN_QQ_IDS=你的QQ号
   CLAUDE_CONFIG_DIR=/home/your-user/.claude
   CLAUDE_CLI_COMMAND=claude
   CLAUDE_TIMEOUT_SECONDS=180
   CLAUDE_WORKDIR=/workspace
   SHELL_ALLOWED_PREFIXES=pwd,ls,git status
   ```

7. 启动服务：

   ```bash
   docker compose up -d --build
   ```

8. 查看日志：

   ```bash
   docker compose logs -f agent-qq
   ```

9. 向机器人 QQ 私聊测试：

   ```text
   /help
   /status
   /ask 你好
   ```

如果 `/status` 和 `/ask` 都能正常返回，则部署完成。
