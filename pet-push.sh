#!/bin/bash
# xShield Pet — kodu GELİŞTİRME BİLGİSAYARINDAN VPS'e yükler ve kurulumu çalıştırır.
# (VPS'in GitHub erişimi olmadığı için kod git pull yerine buradan kopyalanır.)
#
#   ./pet-push.sh                       # xshield reposundaki varsayılan branch'ten
#   PET_REF=main ./pet-push.sh          # başka bir branch/commit'ten
#
# Ortam: VPS_HOST (varsayılan rootx@77.223.130.51), VPS_KEY (varsayılan ~/.ssh/vps_key),
#        XSHIELD_REPO (varsayılan ../xshield)
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "$0")" && pwd)"
XSHIELD_REPO=${XSHIELD_REPO:-$INFRA_DIR/../xshield}
PET_REF=${PET_REF:-origin/claude/petshop-tenant-platform-34w53o}
VPS_HOST=${VPS_HOST:-rootx@77.223.130.51}
VPS_KEY=${VPS_KEY:-$HOME/.ssh/vps_key}
SSH=(ssh -i "$VPS_KEY" -o BatchMode=yes "$VPS_HOST")

echo "==> [1/3] Kod hazırlanıyor ($PET_REF)"
git -C "$XSHIELD_REPO" fetch -q origin
REV=$(git -C "$XSHIELD_REPO" rev-parse --short "$PET_REF")
git -C "$XSHIELD_REPO" cat-file -e "$PET_REF:pet/Dockerfile" || { echo "✗ $PET_REF içinde pet/ yok" >&2; exit 1; }
echo "   commit: $(git -C "$XSHIELD_REPO" log --oneline -1 "$PET_REF")"

echo "==> [2/3] VPS'e yükleniyor (~/xshield/pet-app)"
# Önce yanına açılır, sonra yer değiştirilir; bir önceki sürüm pet-app.prev olarak kalır.
git -C "$XSHIELD_REPO" archive --format=tar "$PET_REF" pet | "${SSH[@]}" "
  set -e
  cd ~/xshield
  rm -rf pet-app.new && mkdir pet-app.new
  tar -x -C pet-app.new --strip-components=1
  echo '$REV' > pet-app.new/.deployed-rev
  if [ -d pet-app ]; then rm -rf pet-app.prev && mv pet-app pet-app.prev; fi
  mv pet-app.new pet-app
  echo \"   yüklendi: \$(cat pet-app/.deployed-rev)\"
"

echo "==> [3/3] Kurulum (deploy-pet.sh)"
"${SSH[@]}" "cd ~/xshield/infra && ./deploy-pet.sh"
