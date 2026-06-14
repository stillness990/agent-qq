# agent-qq 重构升级报告

**日期：** 2026-06-14
**版本：** v2.0.1（纯指令驱动架构 + AI 交互收束）
**触发：** 用户需求规格书
**修订：** v2.0.0→v2.0.1 删除 `/ask` `/code`，确保仅 `/plan` 可调 AI

---

## 一、升级概要

本次重构将 agent-qq 从 **"AI 兜底"混合架构** 彻底升级为 **"纯指令驱动（Command-Driven）"架构**。所有 QQ 消息由底层脚本解析路由，**不再有任何消息被透传给 AI 做自然语言兜底处理**。

**核心原则：仅 `/plan <自然语言>` 能与 AI 交互，其余所有命令均为纯脚本/子进程执行，零 AI Token 消耗。**

### 架构对比

| 维度 | v1.x（旧） | v2.0.1（新） |
|------|-----------|-----------|
| 路由模式 | if-elif 链 + AI 兜底 | 指令字典 + 零 Token 拦截 |
| 未知消息 | 全部传给 Claude Code | 返回 `/help` 提示 |
| AI 交互入口 | 3 个（/ask /code + 兜底） | **1 个（仅 /plan 系列）** |
| 命令数量 | 7 条（含预留） | 14 条（9 条纯脚本可执行） |
| 任务持久化 | 纯内存 | 内存 + JSON 文件双写 |
| 异常处理 | 无 | 三路检测 + 熔断 + 回滚 |
| 状态监控 | 无 | 后台 5s 轮询巡检 |
| 日志管理 | 无自动清理 | 条数限制 + 终态清理 |

---

## 二、新增模块

### 1. Plan 状态机 (`plan_state.py` — 190 行)

完整实现 5 条 `/plan` 命令生命周期：

```
/plan <描述>  →  PENDING  →  pending_plan.json
/plan-status  →  查看待确认计划
/plan-start   →  EXECUTED  →  执行 + 归档 plan_history.json
/plan-cancel  →  CANCELLED →  丢弃 + 归档
/plan-log     →  查询历史（含状态图标）
```

**安全机制：**
- 同一时间仅允许 1 个待确认计划
- /plan 仅返回 AI 大纲，不执行任何操作
- /plan-start 才真正下发 AI 执行
- 所有状态变更自动归档到 `plan_history.json`

### 2. 状态日志 (`task_status_log.py` — 155 行)

- 独立 `data/task_status_log.json`，与运行日志解耦
- 任务创建/状态变更/异常均实时写入
- 支持按状态过滤查询活跃任务
- 修复了旧版 /status 在执行期间查不到任务的 Bug

### 3. 后台监控 (`task_monitor.py` — 140 行)

- 每 5s 轮询 `task_status_log.json`
- 纯脚本巡检，零 AI Token 消耗
- 检测运行中任务的健康状态
- 内置网络质量测试（ping github.com + baidu.com → 优/良/差）

### 4. 熔断器 (`circuit_breaker.py` — 130 行)

三种异常检测通道：

| 通道 | 检测方式 | 阈值 |
|------|---------|------|
| Token 耗尽 | Claude 返回值关键词匹配（10 个模式） | 1 次触发 |
| 网络异常 | 连续连接错误计数 | 3 次连续 |
| 任务超时 | 运行时长 vs 阈值 | 30 分钟 |

熔断后：终止任务 → QQ 通知 → 状态标记 EXCEPTION → 归档 plan_history.json

### 5. 日志轮转 (`log_rotator.py` — 55 行)

- `plan_history.json`：超过 50 条自动裁剪最早记录
- `task_status_log.json`：completed/cancelled 超过 24h 自动清理
- 启动时自动执行一次清理

---

## 三、修改模块

### command_router.py
- **指令字典化**：`COMMANDS` dict 集中管理全部 14 条路由
- **删除 AI 兜底**：`route()` 末尾不再调用 `self._claude.ask(text)`
- **删除 /ask 和 /code**：v2.0.1 中彻底移除这两个 AI 交互通道，确保仅 /plan 可调 AI
- **新增 10 条命令**：/ping /network /clear /token /weather /kill /plan /plan-start /plan-cancel /plan-status /plan-log
- **AI 审计**：command_router.py 中 7 处 `self._claude` 调用，仅 2 处为 AI 调用（均属 /plan），其余为纯脚本/子进程
- **权限控制**：/shell /log 管理员检查

### task_registry.py
- 集成 `TaskStatusLog`，任务创建/完成/异常均落盘
- 新增 `plan_id` 字段关联 Plan 记录
- `format_status()` 合并内存 + 持久化双源（修复 /status Bug）
- 新增 `mark_exception()` 供熔断器调用

### bot.py
- 初始化全部新组件（PlanStateMachine / CircuitBreaker / TaskMonitor / LogRotator）
- 启动时执行日志轮转清理
- 启动后台 TaskMonitor
- 熔断通知回调接入 QQ 发送链路

### config.py
- 新增 6 个配置组共 12 个字段

---

## 四、代码规模

| 指标 | 数值 |
|------|------|
| 修改文件 | 6 个 |
| 新建文件 | 5 个 |
| 新增代码 | +2,284 行 |
| 删除代码 | -265 行 |
| 项目总行数 | 3,546 行 Python |
| 新增测试用例 | +16（共 53 个） |

---

## 五、AI 交互审计（v2.0.1 强化）

对 `command_router.py` 中全部 `self._claude` 调用逐行审计：

| 行号 | 方法 | 命令 | 是否 AI？ |
|------|------|------|-----------|
| 182 | `.status()` | `/status` | ❌ 仅 `claude --version` |
| 244 | `._is_allowed_shell()` | `/shell` | ❌ 本地白名单匹配 |
| 251 | `.shell()` | `/shell` | ❌ `create_subprocess_shell` |
| **293** | **`.ask()`** | **`/plan`** | ✅ **唯一 AI 入口** |
| **343** | **`.ask()`** | **`/plan-start`** | ✅ **Plan 状态机延续** |
| 425 | `.status()` | `/token` | ❌ 仅 `claude --version` |

> **结论：除 /plan [自然语言] 系列外，没有任何代码路径触发 AI 调用。**

---

## 六、服务验证

```
systemctl --user restart agent-qq → 成功（14:00 CST）
启动日志：
  Log rotator startup cleanup: removed 0 terminal status entries
  TaskMonitor started (poll every 5s)
  Connected to OneBot: ws://127.0.0.1:3001
bot.py 含 12 处 v2.0 组件引用（TaskMonitor/PlanStateMachine/CircuitBreaker 等）
command_router.py: _cmd_ask=0, _cmd_code=0（已删除）
```

---

## 七、风险与回滚

| 风险点 | 缓解措施 |
|--------|---------|
| /ask /code 已删除 | 用户需通过 /plan 描述需求来触发 AI，更安全可控 |
| 新命令未完全测试 | 53 个测试覆盖核心路径，可继续通过 QQ 实测 |
| SSH/GH 推送依赖代理 | 环境有 HTTP 代理 127.0.0.1:7897，已验证可用 |
| 配置文件兼容 | 所有新配置均有默认值，旧 .env 无需修改即可运行 |

回滚方式：`git revert` 本次提交即可恢复 v1.x 架构。
