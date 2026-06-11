# agent-qq API 接口说明

agent-qq 对外不提供 HTTP API，主要通过 OneBot v11 WebSocket 与 NapCat 通信。

## OneBot 接收事件

当前处理私聊消息：

```json
{
  "post_type": "message",
  "message_type": "private",
  "message_id": 123,
  "user_id": 456,
  "message": "你好"
}
```

## OneBot 发送消息

调用 OneBot 动作：

```json
{
  "action": "send_private_msg",
  "params": {
    "user_id": 456,
    "message": "回复内容"
  },
  "echo": "agent-qq-1"
}
```

## 内部命令接口

| 命令 | 权限 | 说明 |
|---|---|---|
| `/help` | 所有人 | 查看帮助 |
| `/status` | 所有人 | 查看状态 |
| `/ask 文本` | 所有人 | 调用 Claude Code 回答 |
| `/log` | 管理员 | 查看日志位置 |
| `/shell 命令` | 管理员 | 执行白名单 Shell 命令 |
| `/code 需求` | 管理员 | 调用 Claude Code 执行代码任务 |

## 预留接口

- `/search`
- `/agent`
- `/mcp`
- `/rag`
- `/workflow`
