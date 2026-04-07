#!/usr/bin/env bash
# start_telegram.sh — Start Telegram bot as background service
#
# Usage: bash scripts/start_telegram.sh
#
# Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars set

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/.pids"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "[⚠] TELEGRAM_BOT_TOKEN not set. Telegram bot will not start."
    exit 1
fi

echo "[→] Starting Telegram bot..."

cd "$PROJECT_ROOT"
uv run python -m core.telegram_bot &> /tmp/telegram_bot.log &
pid=$!

if [ -f "$PID_FILE" ]; then
    echo "telegram_bot=$pid" >> "$PID_FILE"
fi

echo "[✔] Telegram bot started (PID $pid)"
echo "[→] Logs: /tmp/telegram_bot.log"
