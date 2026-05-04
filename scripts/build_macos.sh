#!/usr/bin/env bash
# scripts/build_macos.sh
# Build portable macOS distribution of Search Query Tool
# Usage: ./scripts/build_macos.sh

set -euo pipefail

echo "=== Search Query Tool - macOS Build ==="

# Ensure we are in the project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 1. Sync dependencies
echo ""
echo "[1/5] Syncing dependencies..."
uv sync --group dev

# 2. Compile-check all Python
echo ""
echo "[2/5] Compile-checking source..."
uv run python -m compileall app.py src tests -q

# 3. Run tests
echo ""
echo "[3/5] Running tests..."
uv run python -m unittest discover -s tests

# 4. Build with PyInstaller via spec file (single source of truth)
echo ""
echo "[4/5] Building with PyInstaller (onedir)..."
uv run pyinstaller SearchTool.spec --noconfirm --clean

# 5. Assemble portable_dist from the PyInstaller output
echo ""
echo "[5/5] Assembling portable distribution..."
uv run python build.py

echo ""
echo "=== Build complete! ==="
echo "Output: portable_dist/SearchQueryTool/"

# Detect architecture
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
    echo "Architecture: Apple Silicon (arm64)"
elif [ "$ARCH" = "x86_64" ]; then
    echo "Architecture: Intel (x86_64)"
fi
echo "Zip this folder to distribute: portable_dist/SearchQueryTool/"
