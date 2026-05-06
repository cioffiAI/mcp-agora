# MCP Agora — Installer (Windows PowerShell)
# ============================================
# Usage: irm https://raw.githubusercontent.com/cioffiAI/mcp-agora/main/scripts/install.ps1 | iex
#
# Installs MCP Agora via uv tool, which creates an isolated venv
# and makes the `agora` command available globally.

param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$HAS_UV = Get-Command uv -ErrorAction SilentlyContinue

if (-not $HAS_UV) {
    Write-Host ">>> Installing uv (Python package manager)..."
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User")
}

if ($Dev) {
    Write-Host ">>> Installing mcp-agora in dev mode (editable)..."
    git clone https://github.com/cioffiAI/mcp-agora.git "$env:TEMP\mcp-agora"
    Set-Location "$env:TEMP\mcp-agora"
    uv sync --dev
    Write-Host "[OK] Dev install complete. cd $env:TEMP\mcp-agora && uv run agora"
} else {
    Write-Host ">>> Installing mcp-agora from PyPI..."
    uv tool install mcp-agora
    Write-Host "[OK] MCP Agora installed!"
    Write-Host ""
    Write-Host "    Run: uv run agora"
    Write-Host "    Or:  agora (if .local\bin is in PATH)"
}
