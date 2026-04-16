# xShield Infrastructure

Tüm xShield servislerini tek noktadan yöneten nginx + docker-compose orchestration reposu.

## VPS Dizin Yapısı

```
~/xshield/
├── web/        → git clone utonguc/xshield-web
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
