# FAQ

## 1. 为什么不直接调用 Claude API？

本项目目标是使用本机 Claude Code CLI 作为智能执行层。Python Gateway 只负责 QQ 消息接入、命令路由和结果返回。

## 2. 为什么 Docker 里也需要 Claude Code CLI？

容器内运行 Python Gateway 时，需要能执行 `claude -p` 命令，因此 Dockerfile 安装 Claude Code CLI，并挂载宿主机 `.claude` 配置。

## 3. 404 或连接失败怎么办？

检查 NapCat OneBot WebSocket 是否启动，端口是否正确。

宿主机运行：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

Docker 运行：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

## 4. /shell 为什么不能执行某些命令？

为了安全，`/shell` 只允许管理员使用，并且只允许白名单命令前缀。修改：

```env
SHELL_ALLOWED_PREFIXES=pwd,ls,git status
```

## 5. 如何查看日志？

```bash
docker compose logs -f agent-qq
```

或查看：

```text
logs/agent-qq.log
```

## 6. 如何新增知识库？

在 `plugins/rag/` 下实现 `RagRetriever` 接口，然后在命令路由中接入 `/rag` 命令。
