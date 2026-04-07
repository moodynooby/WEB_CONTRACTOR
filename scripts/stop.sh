#!/usr/bin/env bash
# stop.sh — Clean shutdown of all Web Contractor services
#
# Usage: bash scripts/stop.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/.pids"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
info() { echo -e "[→] $1"; }

if [ ! -f "$PID_FILE" ]; then
    warn "No PID file found — services may not be running"
    info "Attempting to kill by process name..."

    pkill -f "streamlit run streamlit_app" 2>/dev/null && log "Stopped Streamlit" || warn "Streamlit not running"
    pkill -f "cloudflared" 2>/dev/null && log "Stopped cloudflared" || warn "cloudflared not running"
    pkill -f "telegram_bot" 2>/dev/null && log "Stopped Telegram bot" || warn "Telegram bot not running"
    exit 0
fi

info "Stopping services from PID file..."

while IFS='=' read -r name pid; do
    if kill -0 "$pid" 2>/dev/null; then
        info "Stopping $name (PID $pid)..."
        kill "$pid" 2>/dev/null && log "Stopped $name" || warn "Failed to stop $name"
    else
        warn "$name (PID $pid) not running"
    fi
done < "$PID_FILE"

rm -f "$PID_FILE" "$PROJECT_ROOT/.tunnel_url" /tmp/cloudflared_tunnel.log
log "Cleanup complete"
