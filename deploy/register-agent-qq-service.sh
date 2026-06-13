#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="agent-qq"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_USER="${RUN_USER:-agent-qq}"
RUN_GROUP="${RUN_GROUP:-$RUN_USER}"
UNIT_SOURCE="$PROJECT_DIR/deploy/systemd/${SERVICE_NAME}.service"
UNIT_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
BOT_ENTRY="$PROJECT_DIR/bot.py"

info() {
  printf '[INFO] %s\n' "$*"
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

fail() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "文件不存在：$path"
}

require_executable() {
  local path="$1"
  [[ -x "$path" ]] || fail "文件不存在或不可执行：$path"
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 sudo 运行：sudo bash $0"
fi

require_file "$BOT_ENTRY"
require_executable "$PYTHON_BIN"
require_file "$UNIT_SOURCE"

info "项目目录：$PROJECT_DIR"
info "服务文件源：$UNIT_SOURCE"
info "服务文件目标：$UNIT_TARGET"

if pgrep -f "$PYTHON_BIN $BOT_ENTRY" >/dev/null 2>&1 || pgrep -f "python.*$BOT_ENTRY" >/dev/null 2>&1; then
  warn "检测到已有手动 bot.py 进程。为避免重复连接 OneBot，将尝试停止它。"
  pkill -f "$PYTHON_BIN $BOT_ENTRY" || true
  pkill -f "python.*$BOT_ENTRY" || true
  sleep 2
fi

sed \
  -e "s#__PROJECT_DIR__#$PROJECT_DIR#g" \
  -e "s#__PYTHON_BIN__#$PYTHON_BIN#g" \
  -e "s#__RUN_USER__#$RUN_USER#g" \
  -e "s#__RUN_GROUP__#$RUN_GROUP#g" \
  "$UNIT_SOURCE" > "$UNIT_TARGET"
chmod 0644 "$UNIT_TARGET"

info "重新加载 systemd 配置"
systemctl daemon-reload

info "设置开机自启"
systemctl enable "$SERVICE_NAME"

info "重启服务"
systemctl restart "$SERVICE_NAME"

info "服务状态"
systemctl --no-pager --full status "$SERVICE_NAME"

info "注册完成。常用命令："
printf '  sudo systemctl status %s --no-pager\n' "$SERVICE_NAME"
printf '  journalctl -u %s -f\n' "$SERVICE_NAME"
printf '  sudo systemctl restart %s\n' "$SERVICE_NAME"
printf '  sudo systemctl stop %s\n' "$SERVICE_NAME"
