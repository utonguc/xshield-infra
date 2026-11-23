#!/usr/bin/env bash
# xShield Pet — mağazaların doğrulanmış alan adlarını nginx'e ekler.
#
# pet_app'ten doğrulanmış alan adı listesini alır, nginx/pet-domains/custom.conf dosyasına yazar,
# yalnızca değişiklik varsa `nginx -t` ile test edip nginx'i yeniden yükler. Hata olursa eski
# dosyaya döner. Tekrar çalıştırmak güvenlidir.
#
# Kurulum: deploy-pet.sh cron'a ekler (her 2 dakikada bir, log: logs/pet-domains.log).
# Log yolu çalıştıran kullanıcının yazabileceği bir yer olmalı; yoksa cron sessizce hiç çalıştırmaz.
set -euo pipefail

cd "$(dirname "$0")"
DIR=nginx/pet-domains
OUT="$DIR/custom.conf"
APP=${PET_APP_CONTAINER:-pet_app}
NGINX=${NGINX_CONTAINER:-xshield_nginx}

# Token'ı .env'den oku (betik cron'dan çalışırken ortam değişkeni olmaz).
TOKEN=${PET_INTERNAL_TOKEN:-$(grep -E '^PET_INTERNAL_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')}
if [ -z "$TOKEN" ] || [ "$TOKEN" = "CHANGE_ME" ]; then
  echo "$(date -Is) PET_INTERNAL_TOKEN tanımlı değil (.env)" >&2
  exit 1
fi

mkdir -p "$DIR"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Konteynerin içinden iste: uç nokta dışarıya açık olsa da token'sız 401 döner.
if ! docker exec "$APP" wget -q -O - --header "Authorization: Bearer $TOKEN" http://127.0.0.1:3000/api/domains/nginx >"$TMP"; then
  echo "$(date -Is) $APP'ten alan adı listesi alınamadı" >&2
  exit 1
fi

# Yalnızca beklenen satırlar: yorum veya "server_name alan.adi;"
if grep -vqE '^(#.*|server_name [a-z0-9.-]+;)?$' "$TMP"; then
  echo "$(date -Is) Beklenmeyen içerik, nginx'e yazılmadı" >&2
  exit 1
fi

if [ -f "$OUT" ] && cmp -s "$TMP" "$OUT"; then
  exit 0 # değişiklik yok
fi

BACKUP=""
if [ -f "$OUT" ]; then
  BACKUP=$(mktemp)
  cp "$OUT" "$BACKUP"
fi
cp "$TMP" "$OUT"
chmod 644 "$OUT"

if docker exec "$NGINX" nginx -t >/dev/null 2>&1; then
  docker exec "$NGINX" nginx -s reload
  echo "$(date -Is) nginx güncellendi: $(grep -c '^server_name' "$OUT" || true) alan adı"
else
  echo "$(date -Is) nginx -t başarısız, eski yapılandırmaya dönülüyor" >&2
  if [ -n "$BACKUP" ]; then cp "$BACKUP" "$OUT"; else rm -f "$OUT"; fi
  exit 1
fi
[ -n "$BACKUP" ] && rm -f "$BACKUP"
exit 0
