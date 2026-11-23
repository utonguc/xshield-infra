#!/bin/bash
# xShield Pet (pet.xshield.com.tr) — VPS'te kurulum / güncelleme. Genelde geliştirme bilgisayarından
# ./pet-push.sh ile çağrılır (kodu ~/xshield/pet-app'e yükleyip bunu çalıştırır).
#
# Ne yapar (tekrar çalıştırmak güvenlidir):
#   1. ~/xshield/pet-app'te kodun olduğunu kontrol eder
#   2. .env'de eksik PET_* değişkenlerini üretir (var olanlara dokunmaz, önce yedek alır)
#   3. pet_db + pet_app'i derleyip başlatır (migration'lar açılışta otomatik)
#   4. nginx'i yeni yapılandırmayla yeniden oluşturur (önce nginx -t)
#   5. Alan adı senkron betiğini cron'a ekler
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$INFRA_DIR/../pet-app"
ENV_FILE="$INFRA_DIR/.env"

step() { echo; echo "==> $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

step "[1/5] Kod kontrol ediliyor"
[ -f "$APP_DIR/Dockerfile" ] || fail "$APP_DIR bulunamadı — önce geliştirme bilgisayarından ./pet-push.sh çalıştırın."
echo "   pet-app: $(cat "$APP_DIR/.deployed-rev" 2>/dev/null || echo 'sürüm bilinmiyor')"

step "[2/5] .env kontrol ediliyor"
[ -f "$ENV_FILE" ] || fail "$ENV_FILE yok."
cp "$ENV_FILE" "$ENV_FILE.bak-$(date +%Y%m%d%H%M%S)"
ensure_var() {
  local name=$1 value=$2
  if grep -qE "^${name}=.+" "$ENV_FILE" && ! grep -qE "^${name}=CHANGE_ME" "$ENV_FILE"; then
    echo "   $name: mevcut"
  else
    sed -i "/^${name}=/d" "$ENV_FILE"
    echo "${name}=${value}" >> "$ENV_FILE"
    echo "   $name: eklendi"
  fi
}
ensure_var PET_DB_PASS "$(openssl rand -hex 24)"
ensure_var PET_INTERNAL_TOKEN "$(openssl rand -hex 24)"
if ! grep -qE "^PET_ADMIN_EMAILS=.+" "$ENV_FILE"; then
  echo "   ! PET_ADMIN_EMAILS boş — /yonetim ekranı için .env'e kendi e-postanızı ekleyip bu betiği tekrar çalıştırın."
fi

step "[3/5] pet_db + pet_app derleniyor ve başlatılıyor"
cd "$INFRA_DIR"
mkdir -p nginx/pet-domains
docker compose --env-file .env up -d --build pet_db pet_app
echo "   pet_app hazır olması bekleniyor…"
for i in $(seq 1 60); do
  if docker exec pet_app wget -q -O /dev/null http://127.0.0.1:3000/ 2>/dev/null; then echo "   pet_app çalışıyor."; break; fi
  [ "$i" = 60 ] && { docker logs --tail 40 pet_app; fail "pet_app 2 dakikada açılmadı (loglar yukarıda)."; }
  sleep 2
done

step "[4/5] nginx yenileniyor"
docker compose --env-file .env up -d --no-deps --force-recreate nginx
sleep 2
docker exec xshield_nginx nginx -t || fail "nginx yapılandırması hatalı — 'docker logs xshield_nginx' ile bakın."
echo "   nginx tamam."

step "[5/5] Alan adı senkronu (cron)"
chmod +x "$INFRA_DIR/sync-pet-domains.sh"
CRON_LINE="*/2 * * * * $INFRA_DIR/sync-pet-domains.sh >> /var/log/xshield-pet-domains.log 2>&1"
if crontab -l 2>/dev/null | grep -qF "sync-pet-domains.sh"; then
  echo "   cron zaten kurulu."
else
  (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
  echo "   cron eklendi."
fi
"$INFRA_DIR/sync-pet-domains.sh" || true

echo
echo "✓ xShield Pet yayında olmalı: https://pet.xshield.com.tr"
echo "  Kontrol: curl -sI -H 'Host: pet.xshield.com.tr' -k https://127.0.0.1/ | head -1"
echo "  Cloudflare'de 'pet' için proxied DNS kaydı yoksa ekleyin."
