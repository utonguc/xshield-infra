# xShield Infrastructure

Tüm xShield servislerini tek noktadan yöneten nginx + docker-compose orchestration reposu.

## VPS Dizin Yapısı

```
~/xshield/
├── web/        → git clone utonguc/xshield-web
├── pet-app/    → xShield Pet (pet.xshield.com.tr) — xshield reposundaki pet/, pet-push.sh ile yüklenir
├── eclinic/    → git clone utonguc/eclinic
├── signed/     → git clone utonguc/signed
├── hotspot/    → git clone utonguc/xshield-hotspot  (yakında)
├── signage/    → git clone utonguc/xshield-signage  (yakında)
└── infra/      → git clone utonguc/xshield-infra    (bu repo)
```

## İlk Kurulum

```bash
# Docker network oluştur
docker network create xshield-net

# SSL sertifikalarını koy
mkdir -p nginx/ssl
cp /path/to/cert.crt nginx/ssl/selfsigned.crt
cp /path/to/cert.key nginx/ssl/selfsigned.key

# Env dosyasını hazırla
cp .env.example .env
nano .env

# Tüm servisleri ayağa kaldır
docker compose --env-file .env up -d --build
```

## Yeni Servis Ekleme

1. Ürün reposunu clone et: `git clone git@github.com:utonguc/<repo>.git ~/xshield/<isim>/`
2. `docker-compose.yml`'e servis bloğu ekle
3. `nginx/prod.conf`'a domain bloğu ekle
4. `docker compose --env-file .env up -d --build <servis>` 
5. `docker compose --env-file .env up -d --force-recreate nginx`

## Güncelleme

```bash
# Tek servis güncelle
cd ~/xshield/<repo> && git pull
docker compose --env-file .env up -d --build <servis>

# Nginx config güncelle
cd ~/xshield/infra && git pull
docker compose --env-file .env up -d --force-recreate nginx
```

## xShield Pet — mağazaların kendi alan adları

Doğrulanan alan adları `sync-pet-domains.sh` ile nginx'e eklenir (`nginx/pet-domains/custom.conf`, git'e girmez).
Bir kez kurulum:

```bash
# .env: PET_INTERNAL_TOKEN=$(openssl rand -hex 24)  ve gerekirse PET_CF_API_TOKEN / PET_CF_ZONE_ID
# Geliştirme bilgisayarından (kodu yükler, .env'i tamamlar, derler, nginx'i yeniler, cron'u kurar):
./pet-push.sh
```

SSL için Cloudflare'de **SSL/TLS → Custom Hostnames** (Cloudflare for SaaS) etkinleştirilir ve fallback origin
olarak `pet.xshield.com.tr` seçilir. `PET_CF_API_TOKEN` + `PET_CF_ZONE_ID` tanımlıysa alan adları oraya
otomatik eklenir; tanımlı değilse `/yonetim` sayfasında görünen alan adları panelden elle eklenir.
