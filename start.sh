#!/usr/bin/env bash
#===========================================================================
# agent-qq 一键启动脚本 v2
#
# 用法:
#   ./start.sh              → 启动（已有实例则跳过）
#   ./start.sh --restart    → 先停旧进程，再启动
#   ./start.sh --stop       → 停止所有服务
#   ./start.sh --status     → 查看运行状态
#
# 架构说明:
#   主进程 bot.py → OneBot 事件循环 + 命令路由 + 调度器 + 清理器
#   子进程 bot.py → WorkerPool (4 并行 Worker)
#   2 个 bot.py 进程是正常现象（WorkerPool 由 multiprocessing 创建）
#===========================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
NAPCAT_LAUNCHER="${NAPCAT_LAUNCHER:-$HOME/.local/bin/napcat-qq}"
ONEBOT_PORT="${ONEBOT_PORT:-3001}"
WEBUI_PORT="${WEBUI_PORT:-6099}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

#-------------------------------------------------------------------
# 停止所有 agent-qq 进程
#-------------------------------------------------------------------
stop_all() {
  echo "停止 agent-qq 所有进程..."
  local killed=0

  # 先尝试优雅关闭（SIGTERM）
  for pid in $(pgrep -f "$PROJECT_DIR/.venv/bin/python.*bot.py" 2>/dev/null || true); do
    kill "$pid" 2>/dev/null && ((killed++))
  done
  sleep 1.5

  # 残留的强制 SIGKILL
  for pid in $(pgrep -f "$PROJECT_DIR/.venv/bin/python.*bot.py" 2>/dev/null || true); do
    kill -9 "$pid" 2>/dev/null && ((killed++))
  done

  # 停止启动脚本
  for pid in $(pgrep -f "start_agent_qq.sh" 2>/dev/null || true); do
    kill -9 "$pid" 2>/dev/null && ((killed++))
  done

  sleep 0.5
  echo "已终止 $killed 个进程"
}

#-------------------------------------------------------------------
# 查看状态
#-------------------------------------------------------------------
show_status() {
  echo ""
  echo "════════════════════════════════════════════"
  echo "  agent-qq 运行状态"
  echo "════════════════════════════════════════════"

  # ── bot.py 进程 ──
  local bot_pids=($(pgrep -f "$PROJECT_DIR/.venv/bin/python.*bot.py" 2>/dev/null || true))
  local bot_count=${#bot_pids[@]}

  if [[ $bot_count -eq 0 ]]; then
    fail "bot.py          未运行"
  elif [[ $bot_count -eq 1 ]]; then
    ok "bot.py 主进程    PID: ${bot_pids[0]}"
    warn "WorkerPool      未检测到（可能未启用或启动失败）"
  elif [[ $bot_count -eq 2 ]]; then
    # 区分主进程与子进程
    local main_pid worker_pid
    for p in "${bot_pids[@]}"; do
      local ppid=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
      if [[ "$ppid" == "950" ]] || [[ "$ppid" == "1" ]] || ps -o cmd= -p "$ppid" 2>/dev/null | grep -q "systemd"; then
        main_pid=$p
      else
        worker_pid=$p
      fi
    done
    [[ -n "${main_pid:-}" ]] && ok "bot.py 主进程    PID: $main_pid"
    [[ -n "${worker_pid:-}" ]] && ok "WorkerPool 子进程 PID: $worker_pid (并行 4 Worker)"
  else
    warn "bot.py 进程异常 数量: $bot_count"
    for p in "${bot_pids[@]}"; do
      echo "  - PID: $p"
    done
  fi

  # ── NapCat ──
  if pgrep -f 'Napcat/opt/QQ/qq' >/dev/null 2>&1; then
    ok "NapCat/QQ       已运行"
  elif ss -ltn 2>/dev/null | grep -qE "[.:]${WEBUI_PORT}[[:space:]]"; then
    ok "NapCat WebUI     端口 $WEBUI_PORT 就绪"
  else
    warn "NapCat/QQ       未检测到"
  fi

  # ── 端口 ──
  if ss -ltn 2>/dev/null | grep -qE "[.:]${ONEBOT_PORT}[[:space:]]"; then
    ok "OneBot 端口       $ONEBOT_PORT 就绪"
  else
    fail "OneBot 端口       $ONEBOT_PORT 未监听"
  fi

  # ── 通知 Hook ──
  local hook_pid=$(pgrep -f "claude_notify_hook.py monitor" 2>/dev/null | head -1 || true)
  if [[ -n "$hook_pid" ]]; then
    ok "通知 Hook        PID: $hook_pid"
  else
    info "通知 Hook        bot 启动后自动拉起"
  fi

  # ── 数据文件 ──
  local data_dir="${PLAN_DATA_DIR:-$PROJECT_DIR/data}"
  if [[ -f "$data_dir/worker_state.json" ]]; then
    local idle=$(grep -c '"idle"' "$data_dir/worker_state.json" 2>/dev/null) || idle=0
    local busy=$(grep -c '"busy"' "$data_dir/worker_state.json" 2>/dev/null) || busy=0
    info "Worker 状态      idle=${idle:-0} busy=${busy:-0}"
  fi
  if [[ -f "$data_dir/task_queue.json" ]] && [[ -s "$data_dir/task_queue.json" ]]; then
    local content=$(cat "$data_dir/task_queue.json" 2>/dev/null)
    if [[ "$content" != "[]" ]]; then
      local pending=$(echo "$content" | grep -c '"pending"' 2>/dev/null) || pending=0
      local running=$(echo "$content" | grep -c '"running"' 2>/dev/null) || running=0
      [[ ${pending:-0} -gt 0 || ${running:-0} -gt 0 ]] && info "任务队列          pending=${pending:-0} running=${running:-0}"
    fi
  fi

  echo ""
}

#-------------------------------------------------------------------
# 启动
#-------------------------------------------------------------------
start_all() {
  echo ""
  echo "════════════════════════════════════════════"
  echo "  agent-qq 一键启动 v2"
  echo "════════════════════════════════════════════"

  # --- 1. 检查 Python ---
  if [[ ! -x "$PYTHON_BIN" ]]; then
    fail "Python 解释器不存在: $PYTHON_BIN"
    exit 1
  fi
  ok "Python: $PYTHON_BIN"

  # --- 2. 检查已有实例（防双开） ---
  local bot_count=$(pgrep -f "$PROJECT_DIR/.venv/bin/python.*bot.py" 2>/dev/null | wc -l || true)
  if [[ $bot_count -gt 0 ]]; then
    warn "bot.py 已在运行（$bot_count 个进程），跳过启动"
    echo "  如需重启请执行: $0 --restart"
    show_status
    return 0
  fi

  # --- 3. 启动 NapCat ---
  if pgrep -f 'Napcat/opt/QQ/qq' >/dev/null 2>&1; then
    ok "NapCat/QQ 已在运行"
  elif ss -ltn 2>/dev/null | grep -qE "[.:]${WEBUI_PORT}[[:space:]]"; then
    ok "NapCat WebUI 端口 $WEBUI_PORT 已就绪（QQ 已运行）"
  else
    echo "启动 NapCat/QQ ..."
    if [[ -x "$NAPCAT_LAUNCHER" ]]; then
      nohup "$NAPCAT_LAUNCHER" -q > logs/napcat.log 2>&1 &
      ok "NapCat 已启动 (PID: $!)"
    else
      warn "未找到 NapCat 启动器 ($NAPCAT_LAUNCHER)，请手动启动 QQ"
    fi
  fi

  # --- 4. 等待 OneBot 端口 ---
  echo -n "等待 OneBot WebSocket ($ONEBOT_PORT)"
  local waited=0
  while ! ss -ltn 2>/dev/null | grep -qE "[.:]${ONEBOT_PORT}[[:space:]]"; do
    if (( waited >= WAIT_SECONDS )); then
      echo ""
      fail "等待 OneBot 端口 $ONEBOT_PORT 超时（${WAIT_SECONDS}s）"
      echo "  请确认 NapCat WebUI (http://127.0.0.1:$WEBUI_PORT/webui) 中已启用 WebSocket Server"
      echo "  地址: 127.0.0.1  端口: $ONEBOT_PORT"
      exit 1
    fi
    echo -n "."
    sleep 2
    waited=$((waited + 2))
  done
  echo ""
  ok "OneBot 端口 $ONEBOT_PORT 就绪 (${waited}s)"

  # --- 5. 启动 bot.py ---
  echo "启动 agent-qq bot.py ..."
  nohup "$PYTHON_BIN" bot.py > logs/agent-qq.log 2>&1 &
  local bot_pid=$!
  ok "bot.py 已启动 (PID: $bot_pid)"

  # --- 6. 等待初始化 ---
  sleep 4
  if ! kill -0 "$bot_pid" 2>/dev/null; then
    fail "bot.py 启动后立即退出，查看日志:"
    tail -20 logs/agent-qq.log
    exit 1
  fi

  # --- 7. 验证组件 ---
  local log_file="logs/agent-qq.log"
  if grep -q "WorkerPool started" "$log_file" 2>/dev/null; then
    ok "WorkerPool 已启动"
  fi
  if grep -q "TaskScheduler started" "$log_file" 2>/dev/null; then
    ok "TaskScheduler 已启动"
  fi
  if grep -q "TaskCleaner started" "$log_file" 2>/dev/null; then
    ok "TaskCleaner 已启动"
  fi
  if grep -q "Connected to OneBot" "$log_file" 2>/dev/null; then
    ok "OneBot 已连接"
  fi
  if grep -q "Recovery:" "$log_file" 2>/dev/null; then
    ok "启动恢复已完成"
  fi

  show_status
  ok "一键启动完成！"
}

#-------------------------------------------------------------------
# 主入口
#-------------------------------------------------------------------
MODE="${1:-start}"

case "$MODE" in
  --restart|restart|-r)
    echo "========== 重启 agent-qq =========="
    stop_all
    echo ""
    start_all
    ;;
  --stop|stop|-s)
    stop_all
    sleep 1
    show_status
    ;;
  --status|status)
    show_status
    ;;
  start|--start)
    start_all
    ;;
  *)
    echo "用法: $0 [start|--restart|--stop|--status]"
    echo ""
    echo "  start      启动服务（默认，已有实例则跳过）"
    echo "  --restart  先停止旧进程再启动"
    echo "  --stop     停止所有服务"
    echo "  --status   查看运行状态"
    echo ""
    echo "架构: 主进程(bot.py) + WorkerPool子进程 = 2个 bot.py 是正常的"
    exit 1
    ;;
esac
