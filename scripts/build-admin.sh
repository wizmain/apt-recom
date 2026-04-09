#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ADMIN_SRC="$PROJECT_ROOT/web/admin"
ADMIN_DEST="$PROJECT_ROOT/web/backend/static/admin"

echo "=== Building admin frontend ==="
cd "$ADMIN_SRC"
npm ci --silent
npm run build

echo "=== Copying to backend static ==="
rm -rf "$ADMIN_DEST"
mkdir -p "$(dirname "$ADMIN_DEST")"
cp -r dist/ "$ADMIN_DEST"

echo "=== Done: $ADMIN_DEST ==="
ls -la "$ADMIN_DEST"
