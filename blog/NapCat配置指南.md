# NapCat 配置指南

## 1. 安装 NapCat QQ

请按 NapCat 官方文档安装并登录 QQ。

## 2. 启用 OneBot v11

在 NapCat 配置中启用 OneBot v11 WebSocket 服务。

推荐配置：

```text
Host: 0.0.0.0
Port: 3001
Access Token: 可选
```

## 3. 网络连通性

如果 agent-qq 在宿主机运行：

```env
ONEBOT_WS_URL=ws://127.0.0.1:3001
```

如果 agent-qq 在 Docker 容器中运行：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```

## 4. 测试

启动 agent-qq 后，向机器人 QQ 私聊发送：

```text
/status
```

如果返回运行状态，说明链路正常。
