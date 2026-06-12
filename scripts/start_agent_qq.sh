#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
WORKSPACE_DIR="$PROJECT_DIR/workspace"
mkdir -p "$LOG_DIR" "$WORKSPACE_DIR"

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
NAPCAT_LAUNCHER="${NAPCAT_LAUNCHER:-$HOME/.local/bin/napcat-qq}"
ONEBOT_HOST="${ONEBOT_HOST:-127.0.0.1}"
ONEBOT_PORT="${ONEBOT_PORT:-3001}"
WEBUI_PORT="${WEBUI_PORT:-6099}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

port_listening() {
  local port="$1"
  ss -ltn 2>/dev/null | grep -qE "[.:]${port}[[:space:]]"
}

wait_for_port() {
  local port="$1"
  local name="$2"
  local waited=0
  while ! port_listening "$port"; do
    if (( waited >= WAIT_SECONDS )); then
      log "等待 ${name} 端口 ${port} 超时。"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  log "${name} 端口 ${port} 已就绪。"
}

start_napcat_if_needed() {
  if port_listening "$WEBUI_PORT" || pgrep -f 'Napcat/opt/QQ/qq' >/dev/null 2>&1; then
    log "NapCat/QQ 已在运行，跳过启动。"
    return 0
  fi

  if [[ ! -x "$NAPCAT_LAUNCHER" ]]; then
    log "找不到 NapCat 启动器：$NAPCAT_LAUNCHER"
    return 1
  fi

  log "启动 NapCat/QQ：$NAPCAT_LAUNCHER"
  nohup "$NAPCAT_LAUNCHER" > "$LOG_DIR/napcat.stdout.log" 2>&1 &
  log "NapCat/QQ 启动命令已执行，PID=$!。如未登录 QQ，请在图形界面完成登录。"
}

start_bot_background_if_needed() {
  if pgrep -f "${PROJECT_DIR}/.venv/bin/python bot.py|python bot.py" >/dev/null 2>&1; then
    log "agent-qq bot.py 已在运行，跳过启动。"
    return 0
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    log "找不到 Python 解释器：$PYTHON_BIN"
    return 1
  fi

  log "后台启动 agent-qq bot.py"
  nohup "$PYTHON_BIN" bot.py > "$LOG_DIR/agent-qq.stdout.log" 2>&1 &
  log "agent-qq 已后台启动，PID=$!。日志：$LOG_DIR/agent-qq.stdout.log"
}

run_foreground_bot() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    log "找不到 Python 解释器：$PYTHON_BIN"
    return 1
  fi
  log "前台启动 agent-qq bot.py"
  exec "$PYTHON_BIN" bot.py
}

MODE="${1:-background}"

start_napcat_if_needed
wait_for_port "$WEBUI_PORT" "NapCat WebUI" || true
wait_for_port "$ONEBOT_PORT" "OneBot WebSocket" || {
  log "OneBot WebSocket 未就绪，请确认 NapCat WebUI 中已启用 WebSocket Server：${ONEBOT_HOST}:${ONEBOT_PORT}。"
  exit 1
}

case "$MODE" in
  --foreground|foreground)
    run_foreground_bot
    ;;
  background|--background)
    start_bot_background_if_needed
    ;;
  *)
    log "未知参数：$MODE。可用：background 或 --foreground"
    exit 2
    ;;
esac
