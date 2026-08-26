#!/bin/bash
# ============================================
# Install Claude Code CLI with Vertex AI
# ============================================
# Installs Claude Code and configures it for
# Google Cloud Vertex AI backend.
#
# Usage:
#   ./scripts/install-claude.sh
# ============================================

set -euo pipefail

echo "Installing Claude Code CLI..."

# Install Claude Code
npm install -g @anthropic-ai/claude-code 2>/dev/null || {
    echo "npm not found, installing via curl..."
    curl -fsSL https://claude.ai/install.sh | sh
}

# Require env vars (do not hardcode secrets)
ANTHROPIC_VERTEX_PROJECT_ID="${ANTHROPIC_VERTEX_PROJECT_ID:?Set ANTHROPIC_VERTEX_PROJECT_ID}"
OPENAI_API_KEY="${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
GITHUB_TOKEN="${GITHUB_TOKEN:?Set GITHUB_TOKEN}"

# Configure Vertex AI backend — write to a restricted env file
ENV_FILE="${HOME}/.config/claude/env"
mkdir -p "$(dirname "$ENV_FILE")"

# Only write if not already configured (avoid duplicates)
if [ ! -f "$ENV_FILE" ] || ! grep -q "CLAUDE_CODE_USE_VERTEX" "$ENV_FILE" 2>/dev/null; then
    cat > "$ENV_FILE" << 'ENVEOF'
export CLAUDE_CODE_USE_VERTEX=1
export CLOUD_ML_REGION=us-east5
ENVEOF
    # Append secret values (expanded at write time)
    cat >> "$ENV_FILE" << EOF
export ANTHROPIC_VERTEX_PROJECT_ID="$ANTHROPIC_VERTEX_PROJECT_ID"
export OPENAI_API_KEY="$OPENAI_API_KEY"
export GITHUB_TOKEN="$GITHUB_TOKEN"
EOF
    chmod 600 "$ENV_FILE"
fi

# Add source line to .bashrc if not already present
if ! grep -q "source.*claude/env" "${HOME}/.bashrc" 2>/dev/null; then
    echo "[ -f \"$ENV_FILE\" ] && source \"$ENV_FILE\"" >> "${HOME}/.bashrc"
fi

# Source it now
export CLAUDE_CODE_USE_VERTEX=1
export CLOUD_ML_REGION=us-east5

echo ""
echo "Claude Code installed and configured."
echo "  Backend: Vertex AI (us-east5)"
echo "  Project: $ANTHROPIC_VERTEX_PROJECT_ID"
echo "  Env file: $ENV_FILE (chmod 600)"
echo ""
echo "Run: source ~/.bashrc && claude"
