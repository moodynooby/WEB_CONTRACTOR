#!/usr/bin/env bash
# setup.sh — One-command reproducible setup for Web Contractor remote access
#
# Usage: bash scripts/setup.sh
#
# What this does:
#   1. Installs Python dependencies via uv
#   2. Downloads cloudflared binary if not present
#   3. Generates Streamlit auth config
#   4. Starts Streamlit on port 8501
#   5. Starts Cloudflare Tunnel
#   6. Prints remote access URL

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
fail() { echo -e "${RED}[✘]${NC} $1"; exit 1; }

# ── Config ──────────────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/.pids"
STREAMLIT_PORT=8501
AUTH_CONFIG="$PROJECT_ROOT/config/auth.yaml"
TUNNEL_LOG="/tmp/cloudflared_tunnel.log"

# ── Cleanup previous runs ──────────────────────────────────────────────
cleanup_previous() {
    if [ -f "$PID_FILE" ]; then
        info "Cleaning up previous PIDs..."
        while IFS='=' read -r name pid; do
            if kill -0 "$pid" 2>/dev/null; then
                warn "Stopping previous $name (PID $pid)..."
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
        sleep 2
    fi
    rm -f "$TUNNEL_LOG"
}

# ── 1. Install Python dependencies ──────────────────────────────────────
install_deps() {
    info "Installing Python dependencies..."
    cd "$PROJECT_ROOT"
    if ! command -v uv &> /dev/null; then
        fail "uv is not installed. Please install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    uv sync || fail "Failed to install Python dependencies"
    log "Python dependencies installed"
}

# ── 2. Download cloudflared ────────────────────────────────────────────
install_cloudflared() {
    if command -v cloudflared &> /dev/null; then
        log "cloudflared already installed: $(which cloudflared)"
        return
    fi

    info "Downloading cloudflared..."
    local cf_bin="$PROJECT_ROOT/bin/cloudflared"
    mkdir -p "$PROJECT_ROOT/bin"

    local arch=""
    case "$(uname -m)" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        armv7l)  arch="arm"  ;;
        *)       fail "Unsupported architecture: $(uname -m)" ;;
    esac

    local os_name=""
    case "$(uname -s)" in
        Linux*)  os_name="linux" ;;
        Darwin*) os_name="darwin" ;;
        *)       fail "Unsupported OS: $(uname -s)" ;;
    esac

    local cf_url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${os_name}-${arch}"
    curl -fsSL "$cf_url" -o "$cf_bin" || fail "Failed to download cloudflared"
    chmod +x "$cf_bin"
    log "cloudflared downloaded to $cf_bin"
}

# ── 3. Generate Streamlit auth config ──────────────────────────────────
generate_auth_config() {
    if [ -f "$AUTH_CONFIG" ]; then
        warn "Auth config already exists at $AUTH_CONFIG, skipping"
        return
    fi

    info "Generating Streamlit auth config..."

    # Default credentials — user should change these
    local username="${STREAMLIT_USERNAME:-admin}"
    local password="${STREAMLIT_PASSWORD:-changeme}"

    python3 "$PROJECT_ROOT/scripts/create_auth.py" \
        --username "$username" \
        --password "$password" \
        --output "$AUTH_CONFIG" || fail "Failed to generate auth config"

    log "Auth config generated at $AUTH_CONFIG"
    warn "Default credentials: username=$username password=$password"
    warn "Change these in $AUTH_CONFIG or re-run with STREAMLIT_USERNAME/STREAMLIT_PASSWORD env vars"
}

# ── 4. Start Streamlit ─────────────────────────────────────────────────
start_streamlit() {
    info "Starting Streamlit on port $STREAMLIT_PORT..."
    cd "$PROJECT_ROOT"
    uv run streamlit run streamlit_app.py \
        --server.port "$STREAMLIT_PORT" \
        --server.headless true \
        --server.enableCORS false \
        --server.enableXsrfProtection true \
        --browser.gatherUsageStats false \
        &> /tmp/streamlit.log &

    local pid=$!
    echo "streamlit=$pid" >> "$PID_FILE"
    log "Streamlit started (PID $pid)"

    # Wait for Streamlit to be ready
    info "Waiting for Streamlit to start..."
    for i in $(seq 1 30); do
        if curl -sf "http://localhost:$STREAMLIT_PORT" > /dev/null 2>&1; then
            log "Streamlit is ready"
            return
        fi
        sleep 1
    done
    warn "Streamlit may not be fully ready yet (timeout after 30s)"
}

# ── 5. Start Cloudflare Tunnel ─────────────────────────────────────────
start_tunnel() {
    info "Starting Cloudflare Tunnel..."
    local cf_bin="cloudflared"
    if [ -f "$PROJECT_ROOT/bin/cloudflared" ]; then
        cf_bin="$PROJECT_ROOT/bin/cloudflared"
    fi

    "$cf_bin" tunnel --url "http://localhost:$STREAMLIT_PORT" 2>&1 | tee "$TUNNEL_LOG" &
    local pid=$!
    echo "cloudflared=$pid" >> "$PID_FILE"
    log "Cloudflare Tunnel started (PID $pid)"

    # Wait for tunnel URL
    info "Waiting for tunnel URL..."
    for i in $(seq 1 15); do
        local url
        url=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1 || true)
        if [ -n "$url" ]; then
            log "Tunnel URL: $url"
            echo "$url" > "$PROJECT_ROOT/.tunnel_url"
            return
        fi
        sleep 1
    done
    warn "Tunnel URL not yet available — check $TUNNEL_LOG for details"
}

# ── 6. Start Telegram Bot (optional) ───────────────────────────────────
start_telegram_bot() {
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
        warn "TELEGRAM_BOT_TOKEN not set, skipping Telegram bot"
        return
    fi

    info "Starting Telegram bot..."
    bash "$PROJECT_ROOT/scripts/start_telegram.sh" &
    log "Telegram bot started"
}

# ── Main ────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   🏗️  Web Contractor — Remote Access Setup              ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    cleanup_previous
    install_deps
    install_cloudflared
    generate_auth_config

    > "$PID_FILE"  # Create empty PID file

    start_streamlit
    start_tunnel
    start_telegram_bot

    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                   ✅ Setup Complete!                     ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    local tunnel_url=""
    if [ -f "$PROJECT_ROOT/.tunnel_url" ]; then
        tunnel_url=$(cat "$PROJECT_ROOT/.tunnel_url")
        echo "📱 Remote URL: $tunnel_url"
    fi
    echo "🔒 Username: ${STREAMLIT_USERNAME:-admin}"
    echo "🔑 Password: ${STREAMLIT_PASSWORD:-changeme}"
    echo ""
    echo "📝 To stop all services: bash scripts/stop.sh"
    echo "📋 To verify setup:      bash scripts/verify.sh"
    echo ""
}

main "$@"
