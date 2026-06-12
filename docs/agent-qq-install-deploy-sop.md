# SOP：agent-qq 安装部署标准操作流程

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | agent-qq 安装部署标准操作流程 |
| 适用项目 | agent-qq |
| 适用环境 | Ubuntu/Linux 服务器、Docker Compose、本地 Python 调试环境 |
| 主要组件 | NapCat QQ、OneBot v11、agent-qq、Claude Code CLI |
| 推荐部署方式 | Docker Compose |
| 参考文档 | `agent-qq完整安装部署流程.md`、`README.md`、`docker-compose.yml`、`.env.example` |

## 2. 目标

本 SOP 用于规范 `agent-qq` 的安装、配置、部署、验证、维护和故障处理流程，确保可以稳定复现以下链路：

```text
QQ
→ NapCat QQ
→ OneBot v11 WebSocket
→ agent-qq Python Gateway
→ Claude Code CLI
→ 返回结果到 QQ 私聊
```

完成本 SOP 后，应达到以下结果：

1. NapCat QQ 使用机器人 QQ 账号在线。
2. OneBot v11 WebSocket 服务正常监听。
3. agent-qq 可以连接 OneBot WebSocket。
4. agent-qq 可以调用 Claude Code CLI。
5. 管理员 QQ 私聊机器人发送 `/help`、`/status`、`/ask` 能获得正常回复。
6. 日志、重启、更新、回滚和故障排查流程清晰可执行。

## 3. 适用范围

### 3.1 适用场景

- 新服务器首次部署 agent-qq。
- 本地开发调试 agent-qq。
- Docker Compose 长期运行 agent-qq。
- 更新 agent-qq 代码后重新部署。
- 排查 OneBot、NapCat、Claude Code CLI 或 QQ 私聊链路异常。

### 3.2 不适用场景

- 群聊消息处理部署；当前版本主要处理 QQ 私聊消息。
- 直接调用 Anthropic API 的部署；本项目通过 Claude Code CLI 调用智能能力。
- 未安装或未登录 Claude Code CLI 的环境。

## 4. 角色与职责

| 角色 | 职责 |
|---|---|
| 部署人员 | 准备服务器、安装依赖、配置 `.env`、启动服务、完成验证 |
| QQ 机器人管理员 | 提供机器人 QQ、管理员 QQ，验证私聊命令 |
| 运维人员 | 维护 NapCat、Docker、日志、重启、备份和故障处理 |
| 开发人员 | 维护代码、测试、发布版本、处理缺陷 |

## 5. 系统架构

### 5.1 核心链路

```text
用户 QQ 私聊
  ↓
机器人 QQ / NapCat QQ
  ↓
OneBot v11 WebSocket Server
  ↓
agent-qq WebSocket Client
  ↓
command_router.py 命令路由
  ↓
claude_client.py 调用 claude -p
  ↓
Claude Code CLI
  ↓
OneBot send_private_msg 返回 QQ 私聊
```

### 5.2 组件说明

| 组件 | 说明 |
|---|---|
| QQ | 用户发送私聊消息 |
| NapCat QQ | 登录机器人 QQ，提供 OneBot v11 WebSocket 服务 |
| OneBot v11 | QQ 与 agent-qq 之间的协议层 |
| agent-qq | Python Gateway，负责连接、重连、去重、命令解析、权限控制、调用 Claude Code |
| Claude Code CLI | 实际执行 `/ask`、`/code` 等智能任务 |
| Docker Compose | 推荐的生产部署方式 |

### 5.3 安全边界

- Python 业务层不直接调用 Claude API。
- `.env` 中不保存 Anthropic API Key。
- 模型选择由宿主机 Claude Code CLI 配置决定。
- Docker 部署时只读挂载宿主机 Claude Code 配置目录。
- `/shell`、`/code` 等高风险命令仅管理员可用。
- `/shell` 必须受白名单限制。

## 6. 前置条件

### 6.1 基础环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Ubuntu 24.04 或其他 Linux 发行版 |
| Python | 推荐 Python 3.12；本地测试可使用 Python 3.11+ |
| Docker | 已安装 Docker Engine |
| Docker Compose | 已安装 Docker Compose v2 |
| Git | 已安装 |
| Node.js/npm | Dockerfile 内会安装；宿主机安装 Claude Code CLI 时需要 |
| NapCat QQ | 已安装，可登录机器人 QQ |
| Claude Code CLI | 宿主机已安装并完成登录配置 |

### 6.2 必备信息清单

部署前先确认并记录以下信息：

| 信息 | 示例 | 说明 |
|---|---|---|
| 机器人 QQ 号 | `<bot_qq_id>` | 登录 NapCat 的 QQ 账号 |
| 管理员 QQ 号 | `<admin_qq_id>` | 允许使用 `/shell`、`/code` 的 QQ 账号 |
| OneBot WebSocket 端口 | `3001` | NapCat OneBot v11 WebSocket Server 端口 |
| OneBot Access Token | 可为空 | NapCat 配置 token 时，`.env` 必须一致 |
| Claude 配置目录 | `/home/your-user/.claude` | 宿主机 Claude Code 配置目录 |
| agent-qq 工作目录 | `/workspace` | Claude Code CLI 和 `/shell` 的执行目录 |

> 注意：`ADMIN_QQ_IDS` 配置的是“发送命令的管理员 QQ”，不是机器人 QQ。

## 7. 标准部署流程：Docker Compose 推荐方式

### 7.1 获取项目代码

```bash
git clone https://github.com/<your-github-user>/agent-qq.git
cd agent-qq
```

如果已经在本机存在项目目录：

```bash
cd /path/to/agent-qq
```

### 7.2 配置 NapCat QQ

1. 启动 NapCat QQ。
2. 使用机器人 QQ 账号完成登录。
3. 打开 NapCat WebUI。
4. 启用 OneBot v11 WebSocket Server。
5. 推荐配置：

```text
Host: 0.0.0.0
Port: 3001
Access Token: 可为空；生产环境建议填写随机长字符串
```

6. 保存配置。
7. 检查端口监听：

```bash
ss -ltn | grep 3001
```

预期结果：能看到 `3001` 端口处于监听状态。

### 7.3 验证宿主机 Claude Code CLI

在宿主机执行：

```bash
claude --version
claude -p "你好，请只回复 OK"
```

预期结果：

- `claude --version` 能输出版本号。
- `claude -p` 能正常返回内容。

如果未登录或不可用，先完成 Claude Code CLI 登录和配置，再继续部署。

### 7.4 创建环境变量文件

```bash
cp .env.example .env
nano .env
```

Docker 部署推荐 `.env`：

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

### 7.5 关键变量说明

| 变量 | 是否必填 | 推荐值 | 说明 |
|---|---:|---|---|
| `ONEBOT_WS_URL` | 是 | `ws://host.docker.internal:3001` | Docker 容器访问宿主机 NapCat 的 OneBot 地址 |
| `ONEBOT_ACCESS_TOKEN` | 否 | 与 NapCat 一致 | NapCat 设置 token 时必填 |
| `ENABLE_PRIVATE_CHAT` | 否 | `true` | 是否响应私聊消息 |
| `ADMIN_QQ_IDS` | 强烈建议 | 管理员 QQ | 多个 QQ 用英文逗号分隔 |
| `CLAUDE_CLI_COMMAND` | 否 | `claude` | 容器内调用的 Claude Code CLI 命令 |
| `CLAUDE_TIMEOUT_SECONDS` | 否 | `180` | 单次 Claude 调用超时时间 |
| `CLAUDE_WORKDIR` | 否 | `/workspace` | Claude Code 和 `/shell` 执行目录 |
| `CLAUDE_CONFIG_DIR` | Docker 必填 | `/home/your-user/.claude` | 宿主机 Claude Code 配置目录 |
| `ENABLE_SHELL_COMMAND` | 否 | 生产按需开启 | 是否允许管理员使用 `/shell` |
| `SHELL_ALLOWED_PREFIXES` | 使用 `/shell` 时必填 | 安全白名单 | `/shell` 允许执行的命令前缀 |
| `MESSAGE_DEDUPE_TTL_SECONDS` | 否 | `300` | 消息去重时间窗口 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `RECONNECT_INITIAL_SECONDS` | 否 | `2` | 首次重连等待秒数 |
| `RECONNECT_MAX_SECONDS` | 否 | `60` | 最大重连等待秒数 |
| `QQ_REPLY_CHUNK_SIZE` | 否 | `1800` | QQ 回复分段长度 |

### 7.6 检查 Docker Compose 配置

项目 `docker-compose.yml` 应包含以下关键配置：

```yaml
services:
  agent-qq:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: agent-qq
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./plugins:/app/plugins
      - ./agents:/app/agents
      - ${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    command: ["python", "bot.py"]
```

建议生产环境额外持久化 `/workspace`：

```yaml
volumes:
  - ./workspace:/workspace
```

否则容器重建后 `/workspace` 中的临时工作内容可能丢失。

### 7.7 构建并启动服务

```bash
docker compose up -d --build
```

查看容器状态：

```bash
docker compose ps
```

查看实时日志：

```bash
docker compose logs -f agent-qq
```

预期日志应包含类似内容：

```text
Connected to OneBot
```

## 8. 本地调试流程：Python 直接运行

适合开发调试或不使用 Docker 的场景。

### 8.1 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果系统没有 `pip` 或 `ensurepip`，可使用 `uv`：

```bash
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

### 8.2 本地运行 `.env` 推荐配置

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

### 8.3 链路预检

检查 OneBot WebSocket：

```bash
python scripts/check_onebot.py
```

覆盖地址检查：

```bash
python scripts/check_onebot.py --url ws://127.0.0.1:3001
python scripts/check_onebot.py --url ws://127.0.0.1:3001 --token 你的token
```

预期输出：

```text
ok: connected to ws://127.0.0.1:3001
```

发送测试私聊：

```bash
python scripts/send_test_private_msg.py --to 你的管理员QQ号 --message "agent-qq OneBot 推送测试"
```

如果 NapCat 配置了 token：

```bash
python scripts/send_test_private_msg.py --to 你的管理员QQ号 --token 你的token
```

### 8.4 启动服务

前台运行：

```bash
python bot.py
```

或使用启动脚本后台运行：

```bash
chmod +x scripts/start_agent_qq.sh
scripts/start_agent_qq.sh background
```

前台运行脚本：

```bash
scripts/start_agent_qq.sh --foreground
```

可覆盖启动脚本变量：

```bash
PYTHON_BIN=/path/to/agent-qq/.venv/bin/python \
NAPCAT_LAUNCHER=$HOME/.local/bin/napcat-qq \
ONEBOT_PORT=3001 \
WEBUI_PORT=6099 \
WAIT_SECONDS=180 \
scripts/start_agent_qq.sh background
```

## 9. 部署后验证

### 9.1 容器状态验证

```bash
docker compose ps
```

预期：`agent-qq` 服务处于 `running` 或 `Up` 状态。

### 9.2 日志验证

```bash
docker compose logs -f agent-qq
```

重点确认：

- 已读取 `.env`。
- 已连接 OneBot WebSocket。
- 没有 Claude Code CLI 调用失败。
- 没有 `.claude` 配置目录挂载错误。
- 没有权限或路径错误。

### 9.3 OneBot 连接验证

```bash
python scripts/check_onebot.py --url ws://127.0.0.1:3001
```

Docker 场景可从宿主机验证 NapCat 端口，容器内部连接通过 `host.docker.internal`。

### 9.4 QQ 私聊验证

用管理员 QQ 私聊机器人 QQ，依次发送：

```text
/help
```

预期：返回可用命令列表。

```text
/status
```

预期返回内容包含：

- agent-qq 正常运行。
- 当前用户是否管理员。
- 私聊支持状态。
- Shell 命令启用状态。
- Claude Code CLI 检查结果。

继续测试 Claude 链路：

```text
/ask 你好，请只回复 OK
```

预期：返回 Claude Code CLI 生成的回答。

管理员命令验证：

```text
/log
/shell pwd
/code 请生成一个最小 Python hello world 示例，只需要给代码块
```

### 9.5 成功判定标准

满足以下条件即可判定部署成功：

1. NapCat QQ 登录在线。
2. OneBot v11 WebSocket 端口可连接。
3. `scripts/check_onebot.py` 输出 `ok`。
4. 宿主机 `claude -p "你好"` 可正常执行。
5. agent-qq 日志出现 `Connected to OneBot`。
6. QQ 私聊 `/help` 能返回命令帮助。
7. QQ 私聊 `/status` 能显示 Claude Code CLI 可用。
8. QQ 私聊 `/ask 你好` 能返回模型回答。

## 10. 常用运维操作

### 10.1 查看状态

```bash
docker compose ps
```

### 10.2 查看日志

```bash
docker compose logs -f agent-qq
```

项目日志文件：

```text
logs/agent-qq.log
```

启动脚本后台日志：

```text
logs/agent-qq.stdout.log
logs/napcat.stdout.log
```

### 10.3 重启服务

```bash
docker compose restart agent-qq
```

### 10.4 停止服务

```bash
docker compose down
```

### 10.5 更新代码后重建

```bash
git pull
docker compose up -d --build
docker compose logs -f agent-qq
```

### 10.6 查看最近日志

```bash
docker compose logs --tail=200 agent-qq
```

### 10.7 检查 Claude Code CLI

宿主机检查：

```bash
claude --version
claude -p "你好，请只回复 OK"
```

容器内检查：

```bash
docker compose exec agent-qq claude --version
docker compose exec agent-qq claude -p "你好，请只回复 OK"
```

## 11. 回滚流程

### 11.1 配置变更回滚

适用于只修改 `.env`、`docker-compose.yml` 或白名单配置后出现异常的场景。

1. 恢复上一个可用配置文件。
2. 重启服务：

```bash
docker compose restart agent-qq
```

3. 查看日志：

```bash
docker compose logs -f agent-qq
```

4. QQ 私聊验证：

```text
/status
/ask 你好
```

### 11.2 代码版本回滚

查看提交历史：

```bash
git log --oneline -n 10
```

回滚到指定提交：

```bash
git checkout <commit_id>
docker compose up -d --build
```

验证完成后，如需恢复分支最新版本：

```bash
git checkout <branch_name>
git pull
docker compose up -d --build
```

### 11.3 Docker 镜像回滚

如果有镜像标签管理，可回滚到旧镜像标签；当前项目默认本地构建，推荐通过 Git 版本回滚后重新构建。

```bash
docker compose down
git checkout <last_good_commit>
docker compose up -d --build
```

## 12. 故障排查

### 12.1 OneBot 连接失败或 404

#### 症状

- 日志显示 WebSocket 连接失败。
- `scripts/check_onebot.py` 返回 failed。
- `/status` 没有回复。

#### 排查步骤

1. 确认 NapCat QQ 已启动并登录。
2. 确认 NapCat 已启用 OneBot v11 WebSocket Server。
3. 确认端口为 `3001`：

```bash
ss -ltn | grep 3001
```

4. 宿主机运行时检查 `.env`：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

5. Docker 运行时检查 `.env`：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

6. 如果 NapCat 配置了 token，确认 `.env` 中一致：

```env
ONEBOT_ACCESS_TOKEN=你的token
```

#### 处理方法

- 修改 OneBot 地址或 token。
- 重启 NapCat OneBot 服务。
- 重启 agent-qq：

```bash
docker compose restart agent-qq
```

### 12.2 Docker 容器无法连接宿主机 NapCat

#### 症状

- 宿主机能访问 `127.0.0.1:3001`，容器内访问失败。

#### 排查步骤

1. 确认 NapCat Host 配置为 `0.0.0.0`，不是仅绑定 `127.0.0.1`。
2. 确认 `docker-compose.yml` 包含：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

3. 确认 `.env` 使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

#### 处理方法

修改配置后重建或重启：

```bash
docker compose up -d --build
```

### 12.3 `/status` 没有回复

#### 排查步骤

1. 查看日志：

```bash
docker compose logs --tail=200 agent-qq
```

2. 确认当前版本只处理私聊消息。
3. 确认发送者与机器人 QQ 是私聊关系。
4. 确认 `ENABLE_PRIVATE_CHAT=true`。
5. 确认 OneBot 收到 `message_type=private` 事件。

#### 处理方法

- 使用私聊而不是群聊测试。
- 修正 `.env` 后重启服务。
- 检查 NapCat OneBot 是否正确上报消息事件。

### 12.4 `/ask` 没有回复或超时

#### 排查步骤

1. 宿主机执行：

```bash
claude -p "你好，请只回复 OK"
```

2. 容器内执行：

```bash
docker compose exec agent-qq claude -p "你好，请只回复 OK"
```

3. 检查 Claude 配置目录是否挂载：

```bash
docker compose exec agent-qq ls -la /root/.claude
```

4. 检查超时时间：

```env
CLAUDE_TIMEOUT_SECONDS=180
```

#### 处理方法

- 在宿主机重新登录 Claude Code CLI。
- 修正 `CLAUDE_CONFIG_DIR`。
- 适当增加 `CLAUDE_TIMEOUT_SECONDS`。
- 重建容器确保 Dockerfile 中已安装 Claude Code CLI。

### 12.5 `/shell` 不能执行某些命令

#### 原因

`/shell` 只允许管理员使用，并且命令必须匹配 `SHELL_ALLOWED_PREFIXES` 白名单。

#### 处理方法

修改 `.env`：

```env
SHELL_ALLOWED_PREFIXES=pwd,ls,git status,python --version,python3 --version,df -h,free -h
```

重启服务：

```bash
docker compose restart agent-qq
```

生产环境不要加入以下高风险命令前缀：

```text
rm,curl,wget,ssh,scp,bash,sh,sudo,chmod,chown
```

### 12.6 日志文件不存在

#### 排查步骤

确认 `logs/` 目录存在：

```bash
mkdir -p logs
ls -ld logs
```

Docker 场景确认挂载：

```yaml
volumes:
  - ./logs:/app/logs
```

#### 处理方法

创建目录后重启：

```bash
mkdir -p logs
docker compose restart agent-qq
```

## 13. 安全检查清单

### 13.1 部署安全

- [ ] `.env` 不提交到公开仓库。
- [ ] `ONEBOT_ACCESS_TOKEN` 使用随机长字符串，且只在 NapCat 和 `.env` 中一致配置。
- [ ] `ADMIN_QQ_IDS` 只包含可信 QQ。
- [ ] `/shell` 仅管理员可用。
- [ ] `/shell` 白名单不包含高危命令。
- [ ] Docker 只读挂载 Claude 配置目录：`/root/.claude:ro`。
- [ ] 不在 Python 业务代码中写入 Anthropic API Key。
- [ ] 不在 `.env` 中配置 Anthropic API Key。

### 13.2 发布前脱敏

发布到公开或半公开仓库前，必须排除：

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

推荐检查命令：

```bash
rg -n "(sk-ant|ANTHROPIC_API_KEY|access_token|ONEBOT_ACCESS_TOKEN|ADMIN_QQ_IDS|password|secret|token|Bearer|[0-9]{6,})" . -S
find . -name '__pycache__' -o -name '*.pyc' -o -name '.env' -o -name 'guild1.db*'
```

命中不一定都是敏感信息，但真实 token、真实 QQ 号、真实路径、日志和数据库必须移除或替换为占位符。

## 14. 测试与验收

### 14.1 单元测试

```bash
python -m pytest -q
```

或：

```bash
.venv/bin/python -m pytest -q
```

### 14.2 语法检查

```bash
python3 -m compileall .
```

### 14.3 Docker 构建验证

```bash
docker compose build
```

### 14.4 端到端验收清单

| 检查项 | 命令/动作 | 预期结果 |
|---|---|---|
| NapCat 登录 | 查看 NapCat 界面 | 机器人 QQ 在线 |
| OneBot 监听 | `ss -ltn \| grep 3001` | 端口监听中 |
| OneBot 连通 | `python scripts/check_onebot.py` | 输出 `ok` |
| Claude CLI | `claude -p "你好"` | 正常返回 |
| Docker 状态 | `docker compose ps` | agent-qq 运行中 |
| 日志 | `docker compose logs -f agent-qq` | 出现连接成功日志 |
| QQ 帮助 | 私聊 `/help` | 返回命令列表 |
| QQ 状态 | 私聊 `/status` | 返回运行状态 |
| Claude 调用 | 私聊 `/ask 你好` | 返回模型回答 |
| 管理员命令 | 私聊 `/shell pwd` | 管理员可执行白名单命令 |

## 15. 最小快速部署清单

仅需快速完成部署时，按以下顺序执行：

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

5. 创建并编辑 `.env`：

```bash
cp .env.example .env
nano .env
```

6. Docker 部署最小配置：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ONEBOT_ACCESS_TOKEN=
ENABLE_PRIVATE_CHAT=true
ADMIN_QQ_IDS=你的QQ号
CLAUDE_CONFIG_DIR=/home/your-user/.claude
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
ENABLE_SHELL_COMMAND=true
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

9. QQ 私聊测试：

```text
/help
/status
/ask 你好
```

如果 `/status` 和 `/ask` 都能正常返回，则部署完成。

## 16. 维护建议

1. 每次修改 `.env` 后必须重启服务。
2. 每次更新代码后执行 `docker compose up -d --build`。
3. 定期检查 `logs/agent-qq.log` 是否持续增长过大，必要时接入 logrotate。
4. 定期验证 Claude Code CLI 登录状态。
5. 不要把 `.env`、日志、数据库、`.claude/settings.local.json` 推送到仓库。
6. 生产环境建议给 OneBot 配置 access token。
7. 生产环境谨慎开启 `/shell`，并严格限制白名单。
8. 建议为 `/workspace` 添加持久化挂载，避免容器重建丢失工作区内容。

## 17. 相关文件

| 文件 | 说明 |
|---|---|
| `agent-qq完整安装部署流程.md` | 原始完整安装部署说明 |
| `README.md` | 项目快速说明 |
| `.env.example` | 环境变量模板 |
| `docker-compose.yml` | Docker Compose 部署配置 |
| `Dockerfile` | 容器镜像构建配置 |
| `bot.py` | 主程序入口 |
| `config.py` | 配置读取 |
| `qq_client.py` | OneBot 客户端 |
| `claude_client.py` | Claude Code CLI 调用封装 |
| `command_router.py` | 命令路由 |
| `scripts/check_onebot.py` | OneBot 连通性检查脚本 |
| `scripts/send_test_private_msg.py` | OneBot 私聊推送测试脚本 |
| `scripts/start_agent_qq.sh` | 本地启动辅助脚本 |

## 18. 标签

#agent-qq #SOP #NapCat #OneBot #ClaudeCode #DockerCompose #QQBot #Deployment #Troubleshooting #Runbook
