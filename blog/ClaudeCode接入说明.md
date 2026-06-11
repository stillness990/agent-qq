# Claude Code 接入说明

## 设计目标

agent-qq 的 Python 业务层不直接调用 Claude API，也不依赖 Anthropic SDK。

智能执行链路为：

```text
Python Gateway
→ claude CLI
→ 本机 Claude Code 配置
→ 已配置模型
```

## 前置检查

宿主机执行：

```bash
claude --version
claude -p "你好"
```

确认 Claude Code CLI 可用。

## 配置项

```env
CLAUDE_CLI_COMMAND=claude
CLAUDE_TIMEOUT_SECONDS=180
CLAUDE_WORKDIR=/workspace
```

## Docker 内使用

Dockerfile 会安装 Claude Code CLI：

```dockerfile
RUN npm install -g @anthropic-ai/claude-code
```

docker-compose 会挂载宿主机配置：

```yaml
${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

## 安全边界

- 不在 Python 业务层保存 Claude API Key。
- 不在 `.env` 中配置 Anthropic API Key。
- 不从业务层选择或硬编码模型。
- 模型选择由 Claude Code CLI 的本机配置决定。
