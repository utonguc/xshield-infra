#!/bin/bash
set -e
BASE=/home/rootx/xshield/infra

echo "=== [1/6] fail2ban + python3 kuruyorum ==="
apt-get update -q && apt-get install -y fail2ban python3

echo "=== [2/6] Nginx log dizini oluşturuyorum ==="
mkdir -p /var/log/xshield-nginx
chown root:adm /var/log/xshield-nginx

echo "=== [3/6] Fail2ban yapılandırması ==="
cp "$BASE/fail2ban-config/jail.local"            /etc/fail2ban/jail.local
cp "$BASE/fail2ban-config/xcut-api-login.conf"   /etc/fail2ban/filter.d/xcut-api-login.conf

echo "=== [4/6] Fail2ban bridge kuruyorum ==="
mkdir -p /opt/fail2ban-bridge
cp "$BASE/fail2ban-bridge/server.py"             /opt/fail2ban-bridge/server.py
chmod +x /opt/fail2ban-bridge/server.py
cp "$BASE/fail2ban-bridge/fail2ban-bridge.service" /etc/systemd/system/fail2ban-bridge.service
systemctl daemon-reload
systemctl enable fail2ban-bridge
systemctl restart fail2ban
systemctl start fail2ban-bridge

echo "=== [5/6] Fail2ban servisi durumu ==="
systemctl is-active fail2ban && echo "fail2ban: OK" || echo "fail2ban: HATA"
sleep 2
systemctl is-active fail2ban-bridge && echo "fail2ban-bridge: OK" || echo "fail2ban-bridge: HATA"

echo "=== [6/6] Nginx container'ını yeniden başlatıyorum (log mount için) ==="
# Bu adım docker-compose'un güncellenmesinden SONRA çalıştırılmalı
# docker compose -f /home/rootx/xshield/infra/docker-compose.yml up -d --force-recreate nginx

echo ""
echo "✓ Kurulum tamamlandı!"
echo "  Fail2ban bridge: http://localhost:7655/ping"
echo "  Nginx log yolu: /var/log/xshield-nginx/"
echo ""
echo "NOT: docker-compose.yml güncellemesi ayrıca yapılacak."
