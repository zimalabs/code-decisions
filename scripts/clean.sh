#!/usr/bin/env bash
# Remove build artifacts.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
find "${REPO_ROOT}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
rm -f "${REPO_ROOT}/.coverage" "${REPO_ROOT}/coverage.xml"
rm -rf "${REPO_ROOT}/htmlcov/"
