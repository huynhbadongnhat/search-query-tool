# scripts/build_windows.ps1
# Build portable Windows distribution of Search Query Tool
# Usage: .\scripts\build_windows.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Search Query Tool - Windows Build ===" -ForegroundColor Cyan

# Ensure we are in the project root
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Push-Location $projectRoot

try {
    # 1. Sync dependencies
    Write-Host "`n[1/5] Syncing dependencies..." -ForegroundColor Yellow
    uv sync --group dev

    # 2. Compile-check all Python
    Write-Host "`n[2/5] Compile-checking source..." -ForegroundColor Yellow
    uv run python -m compileall app.py src tests -q

    # 3. Run tests
    Write-Host "`n[3/5] Running tests..." -ForegroundColor Yellow
    uv run python -m unittest discover -s tests

    # 4. Build with PyInstaller via spec file (single source of truth)
    Write-Host "`n[4/5] Building with PyInstaller (onedir)..." -ForegroundColor Yellow
    uv run pyinstaller SearchTool.spec --noconfirm --clean

    # 5. Assemble portable_dist from the PyInstaller output
    Write-Host "`n[5/5] Assembling portable distribution..." -ForegroundColor Yellow
    uv run python build.py

    Write-Host "`n=== Build complete! ===" -ForegroundColor Green
    Write-Host "Output: portable_dist\SearchQueryTool\" -ForegroundColor Green
}
finally {
    Pop-Location
}
