#!/usr/bin/env bash
# bump-version.sh — update version in all locations
# Usage: ./scripts/bump-version.sh 1.0.0
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <version>" >&2
    exit 1
fi

VERSION="$1"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    echo "Error: '$VERSION' is not valid semver (expected X.Y.Z or X.Y.Z-pre)" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 1. Python source of truth
sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" \
    "$REPO_ROOT/src/decision/_version.py"
echo "  updated src/decision/_version.py"

# 2. Plugin manifest
sed -i '' "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" \
    "$REPO_ROOT/src/.claude-plugin/plugin.json"
echo "  updated src/.claude-plugin/plugin.json"

# 3. Marketplace manifest
sed -i '' "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" \
    "$REPO_ROOT/.claude-plugin/marketplace.json"
echo "  updated .claude-plugin/marketplace.json"

echo ""
echo "Version bumped to $VERSION"
