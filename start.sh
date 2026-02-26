#!/usr/bin/env bash
# ── WhichTicker — Launch Script ──────────────────────────────────────────────
#
# Usage:
#   chmod +x start.sh
#   ./start.sh
#
# Or override env vars inline:
#   ANTHROPIC_API_KEY="sk-ant-..." PORT=9000 ./start.sh
# ─────────────────────────────────────────────────────────────────────────────

# ── Required ─────────────────────────────────────────────────────────────────

# Your Anthropic API key (get one at https://console.anthropic.com)
# Without this, AI recommendations will be disabled (everything else still works).
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# ── Optional ─────────────────────────────────────────────────────────────────

# Port to run on (default: 8060)
export PORT="${PORT:-8060}"

# Set this to any value to disable auto-reload (production mode)
# When unset, the app runs in dev mode with hot-reload enabled.
export RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-}"

# ── Validation ───────────────────────────────────────────────────────────────

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "  ⚠  ANTHROPIC_API_KEY is not set."
    echo "     AI recommendations will be disabled."
    echo "     Set it with: export ANTHROPIC_API_KEY=\"sk-ant-...\""
    echo ""
fi

# ── Launch ───────────────────────────────────────────────────────────────────

echo ""
echo "  +==========================================+"
echo "  |    WhichTicker                           |"
echo "  |    Relative Performance Analyzer         |"
echo "  |    http://localhost:${PORT}                  |"
echo "  +==========================================+"
echo ""

exec uvicorn app:app --host 0.0.0.0 --port "$PORT"
