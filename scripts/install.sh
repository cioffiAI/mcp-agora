#!/usr/bin/env bash
# MCP Agora — Installer (Unix / Linux / macOS)
# ==============================================
# Usage: curl -fsSL https://raw.githubusercontent.com/cioffiAI/mcp-agora/main/scripts/install.sh | sh
#
# Installs MCP Agora via uv tool, which creates an isolated venv
# and makes the `agora` command available globally.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

if ! command -v uv &>/dev/null; then
    echo -e "${BLUE}>>> Installing uv (Python package manager)...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if [ "${1:-}" = "--dev" ]; then
    echo -e "${BLUE}>>> Installing mcp-agora in dev mode...${NC}"
    git clone https://github.com/cioffiAI/mcp-agora.git /tmp/mcp-agora
    cd /tmp/mcp-agora
    uv sync --dev
    echo -e "${GREEN}[OK] Dev install complete. cd /tmp/mcp-agora && uv run agora${NC}"
else
    echo -e "${BLUE}>>> Installing mcp-agora from PyPI...${NC}"
    uv tool install mcp-agora
    echo -e "${GREEN}[OK] MCP Agora installed!${NC}"
    echo ""
    echo "    Run: uv run agora"
fi
