#!/usr/bin/env bash
# Run all engram tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running engram tests..."
echo ""
bash "$SCRIPT_DIR/test_engram.sh"
