#!/bin/bash
set -e

XCUT_DIR="$(cd "$(dirname "$0")/../xcut" && pwd)"
INFRA_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> [1/4] git pull"
cd "$XCUT_DIR"
git pull origin main

echo "==> [2/4] Build"
cd "$INFRA_DIR"
docker compose build xcut_backend xcut_frontend

echo "==> [3/4] Restart"
docker compose up -d xcut_backend xcut_frontend

echo "==> [4/4] nginx reload"
docker exec xshield_nginx nginx -s reload 2>/dev/null || true

echo ""
echo "✓ Deploy tamamlandı."
