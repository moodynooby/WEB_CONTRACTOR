#!/usr/bin/env bash
# verify.sh — Health check for Web Contractor remote setup
#
# Usage: bash scripts/verify.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAMLIT_PORT=8501

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

pass() { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
fail() { echo -e "${RED}[✘]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }

all_ok=true

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   🔍 Web Contractor — Health Check                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Streamlit ────────────────────────────────────────────────
info "Checking Streamlit on port $STREAMLIT_PORT..."
if curl -sf "http://localhost:$STREAMLIT_PORT" > /dev/null 2>&1; then
    pass "Streamlit is responding"
else
    fail "Streamlit is not responding on port $STREAMLIT_PORT"
    all_ok=false
fi

# ── 2. Check cloudflared ──────────────────────────────────────────────
info "Checking cloudflared process..."
if pgrep -f "cloudflared" > /dev/null 2>&1; then
    pass "cloudflared is running"

    # Try to extract tunnel URL
    if [ -f "$PROJECT_ROOT/.tunnel_url" ]; then
        tunnel_url=$(cat "$PROJECT_ROOT/.tunnel_url")
        pass "Tunnel URL: $tunnel_url"
    else
        warn "Tunnel URL not found — check /tmp/cloudflared_tunnel.log"
    fi
else
    fail "cloudflared is not running"
    all_ok=false
fi

# ── 3. Check Telegram bot ─────────────────────────────────────────────
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    info "Checking Telegram bot..."
    if pgrep -f "telegram_bot" > /dev/null 2>&1; then
        pass "Telegram bot is running"
    else
        warn "Telegram bot is not running (may not have been started)"
    fi
fi

# ── 4. Check MongoDB connection ───────────────────────────────────────
info "Checking MongoDB connectivity..."
if cd "$PROJECT_ROOT" && uv run python -c "
from core.db import is_connected, init_db
init_db()
if is_connected():
    print('connected')
else:
    print('disconnected')
" 2>/dev/null | grep -q "connected"; then
    pass "MongoDB is connected"
else
    fail "MongoDB is not connected"
    all_ok=false
fi

# ── 5. Check auth config ──────────────────────────────────────────────
AUTH_CONFIG="$PROJECT_ROOT/config/auth.yaml"
info "Checking auth config..."
if [ -f "$AUTH_CONFIG" ]; then
    pass "Auth config exists at $AUTH_CONFIG"
else
    warn "Auth config not found — run setup.sh to generate"
fi

# ── 6. Check Python dependencies ──────────────────────────────────────
info "Checking Python dependencies..."
if cd "$PROJECT_ROOT" && uv run python -c "import streamlit; import pymongo; import plotly" 2>/dev/null; then
    pass "Core dependencies available"
else
    fail "Some dependencies are missing — run: uv sync"
    all_ok=false
fi

# ── Summary ────────────────────────────────────────────────────────────
echo ""
if [ "$all_ok" = true ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ✅ All checks passed!                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║              ❌ Some checks failed                       ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    info "Fix failed checks and re-run: bash scripts/verify.sh"
fi
echo ""
