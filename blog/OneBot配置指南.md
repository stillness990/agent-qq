# OneBot 配置指南

## OneBot v11 WebSocket

agent-qq 通过 WebSocket 连接 NapCat 提供的 OneBot v11 服务。

## 关键配置

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
ONEBOT_ACCESS_TOKEN=
```

如果 NapCat 配置了 access_token，请同步填写：

```env
ONEBOT_ACCESS_TOKEN=你的token
```

## 支持的事件

当前版本处理：

- `post_type=message`
- `message_type=private`

即私聊消息。

## 支持的动作

当前版本调用：

- `send_private_msg`

用于向用户发送私聊回复。

## 消息格式

支持 OneBot 文本消息：

```json
{
  "type": "text",
  "data": {
    "text": "/ask 你好"
  }
}
```
