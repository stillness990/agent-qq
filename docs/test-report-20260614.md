# agent-qq v2.0.1 测试报告

**日期：** 2026-06-14 14:00 CST
**版本：** v2.0.1（删除 /ask /code，收紧 AI 交互至仅 /plan）
**测试环境：** Python 3.11.15, pytest 8.4.1, Linux 6.8.0-40-generic

---

## 一、测试总览

| 指标 | 数值 |
|------|------|
| 测试文件 | 3 个（test_command_router.py / test_task_registry.py / test_notifications.py） |
| 测试用例总数 | **53** |
| 通过 | **53** ✅ |
| 失败 | **0** |
| 错误 | **0** |
| 执行时间 | 1.10s |

---

## 二、测试分组详情

### 2.1 命令路由测试（33 个用例）🆕 +1

#### 消息解析（5 个）
| 用例 | 状态 |
|------|------|
| `test_private_text_message` — 私聊文本消息正常解析 | ✅ |
| `test_self_message_ignored` — 自己的消息被忽略 | ✅ |
| `test_non_message_event_ignored` — 非消息事件被忽略 | ✅ |
| `test_claude_notification_ignored` — 【Claude】前缀通知被过滤 | ✅ |
| `test_array_message_extraction` — 数组格式消息正确拼接 | ✅ |

#### 去重器（3 个）
| 用例 | 状态 |
|------|------|
| `test_first_message_passes` — 首条消息放行 | ✅ |
| `test_duplicate_blocked` — 重复消息拦截 | ✅ |
| `test_ttl_expires` — TTL 过期后放行 | ✅ |

#### 核心路由（16 个）🆕 +1
| 用例 | 状态 |
|------|------|
| `test_help_lists_all_commands` — /help 列出命令，🆕 验证 /ask /code 不在列表中 | ✅ |
| `test_unknown_command_no_ai_fallback` — 🔴 **未知消息不调用 AI** | ✅ |
| `test_ask_removed_treated_as_unknown` — 🆕 /ask → "未知指令"，AI 未调用 | ✅ |
| `test_code_removed_treated_as_unknown` — 🆕 /code → "未知指令"，AI 未调用 | ✅ |
| `test_ping` — /ping 返回 pong + 在线状态 | ✅ |
| `test_network` — /network 返回优/良/差 | ✅ |
| `test_clear` — /clear 重置上下文 | ✅ |
| `test_token` — /token 查询 Token 信息 | ✅ |
| `test_empty_message_returns_none` — 空白消息不处理 | ✅ |
| `test_stop_no_params_shows_usage` — /stop 无参数显示用法 | ✅ |
| `test_kill_is_stop_alias` — /kill 正确映射到 /stop | ✅ |
| `test_reserved_commands` — 预留命令返回提示 | ✅ |
| `test_non_private_message_ignored` — 群聊消息忽略 | ✅ |
| `test_shell_admin_only` — /shell 非管理员拒绝 | ✅ |
| `test_status_lists_running_task` — /status 显示运行中任务 | ✅ |
| `test_stop_running_task_by_id` — /stop 按 ID 停止任务 | ✅ |

#### Plan 状态机（9 个）
| 用例 | 状态 |
|------|------|
| `test_plan_create_requires_description` — /plan 无参数显示用法 | ✅ |
| `test_plan_create_generates_outline` — /plan 生成大纲 + 提示确认 | ✅ |
| `test_plan_status_when_empty` — 无待确认计划时提示 | ✅ |
| `test_plan_status_shows_pending` — 创建后 /plan-status 可见 | ✅ |
| `test_plan_start_without_pending` — 无计划时 /plan-start 提示 | ✅ |
| `test_plan_cancel_without_pending` — 无计划时 /plan-cancel 提示 | ✅ |
| `test_plan_log` — /plan-log 查询历史 | ✅ |
| `test_plan_duplicate_pending_blocked` — 重复创建计划被阻止 | ✅ |
| `test_plan_cancel_then_log_shows_cancelled` — 完整 create→cancel→log 流程 | ✅ |

---

### 2.2 任务注册表测试（13 个用例）

#### 基础功能（7 个）
| 用例 | 状态 |
|------|------|
| `test_registry_lists_running_tasks` — 运行任务列表 | ✅ |
| `test_registry_filters_by_user` — 用户隔离（非管理员） | ✅ |
| `test_registry_filters_by_user_admin` — 管理员可见全部 | ✅ |
| `test_stop_by_id_cancels_task` — ID 停止 + asyncio 取消 | ✅ |
| `test_stop_by_keyword` — 关键词匹配停止 | ✅ |
| `test_stop_ambiguous_keyword` — 多匹配时返回列表 | ✅ |
| `test_finish_removes_task` — 完成移除 | ✅ |

#### 新增功能（6 个）
| 用例 | 状态 |
|------|------|
| `test_finish_with_custom_status` — 自定义终态 | ✅ |
| `test_count_running` — 计数 | ✅ |
| `test_mark_exception_removes_task` — 异常标记 + 移除 | ✅ |
| `test_task_name_trims_text` — 名称截断 | ✅ |
| `test_registry_with_status_log` — 🆕 持久化集成 | ✅ |
| `test_format_status_includes_persistent_entries` — 🆕 /status 修复验证 | ✅ |
| `test_create_with_plan_id` — 🆕 Plan ID 关联 | ✅ |

---

### 2.3 通知系统测试（7 个用例）

| 用例 | 状态 |
|------|------|
| `test_classify_stage_for_common_tools` — 阶段分类 | ✅ |
| `test_prompt_summary_and_stop_format` — 摘要和停止格式化 | ✅ |
| `test_limiter_stage_cooldown_and_failure_hash` — 限流器 | ✅ |
| `test_state_store_sanitizes_session_and_cleans_expired` — 状态存储 | ✅ |
| `test_service_start_stage_stop_with_anti_spam` — 反垃圾 | ✅ |
| `test_service_allowed_cwd_prefix` — 工作目录白名单 | ✅ |
| `test_parse_hook_event_defaults` — 事件解析 | ✅ |

---

## 三、关键验证点

### 3.1 零 Token 消耗（最高优先级需求）

```
测试用例：test_unknown_command_no_ai_fallback
输入："random gibberish text"
预期：返回帮助提示，不调用 AI
结果：✅ "未知指令「random gibberish text」\n发送 /help 查看可用命令列表。"
验证：router._claude.ask 未被调用
```

### 3.2 /ask /code 删除验证（v2.0.1 新增）

```
测试用例：test_ask_removed_treated_as_unknown
输入："/ask 什么是 Python"
预期：返回 "未知指令"，不调用 AI
结果：✅ 确认为未知指令，router._claude.ask.assert_not_called()

测试用例：test_code_removed_treated_as_unknown
输入："/code 写脚本"
预期：返回 "未知指令"，不调用 AI
结果：✅ 确认为未知指令，router._claude.ask.assert_not_called()

测试用例：test_help_lists_all_commands（v2.0.1 增强）
验证：✅ "/ask" not in result, "/code" not in result
        ✅ "唯一 AI 交互入口" in result
        ✅ "零 AI Token 消耗" in result
```

### 3.3 /plan 状态机完整流程

```
create → status → cancel → log 全链路通过 ✅
重复创建拦截 ✅
空状态查询 ✅
```

### 3.4 /status 修复验证

```
旧版：纯内存，跨进程/延迟查询丢失
新版：内存 + task_status_log.json 双源合并
测试：test_format_status_includes_persistent_entries
      写入持久化条目（不写内存）→ format_status 依然可见 ✅
```

---

## 四、实测建议

以下命令可通过手机 QQ 发送给机器人进行人工验证：

| 命令 | 预期结果 |
|------|---------|
| `/ping` | pong + 时间 + 任务数 |
| `/network` | 网络状态：优/良/差 |
| `/help` | 完整命令列表（不含 /ask /code） |
| `/plan 写一个 Hello World` | 生成大纲 + 提示确认 |
| `/plan-status` | 显示待确认计划 |
| `/plan-cancel` | 取消 |
| `/plan-log` | 显示取消记录 |
| `/status` | 运行状态 |
| `/ask 你好` | 🔴 "未知指令…发送 /help"（已验证删除） |
| `/code test` | 🔴 "未知指令…发送 /help"（已验证删除） |
| `你好`（任意非命令文本） | "未知指令…发送 /help" |
