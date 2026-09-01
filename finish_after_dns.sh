#!/usr/bin/env bash
set -euo pipefail
DOMAIN="ksuapi.xn--e1aikcel5c5a.online"
TARGET_IP="144.76.188.75"
WEBROOT="/var/www/letsencrypt"
APP_PORT="18000"
RESOLVED="$(dig +short "$DOMAIN" A | tail -n1)"
if [ "$RESOLVED" != "$TARGET_IP" ]; then
  echo "DNS_NOT_READY: $DOMAIN resolves to ${RESOLVED:-empty}, expected $TARGET_IP" >&2
  exit 2
fi
mkdir -p "$WEBROOT"
certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" --agree-tos --register-unsafely-without-email --non-interactive
cat > /etc/nginx/sites-available/ksuapi.xn--e1aikcel5c5a.online.conf <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN ksuapi.нейроныч.online;

    location /.well-known/acme-challenge/ {
        root $WEBROOT;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN ksuapi.нейроныч.online;

    client_max_body_size 128m;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
NGINX
nginx -t
systemctl reload nginx
python - <<PY
from pathlib import Path
path = Path(".env")
text = path.read_text()
text = text.replace("TELEGRAM_WEBHOOK_URL=\n", "TELEGRAM_WEBHOOK_URL=https://$DOMAIN\n")
path.write_text(text)
PY

# Preserve the immutable production release image. Never let this maintenance
# helper fall back to ksu-app:local after a SHA-tagged deployment.
app_container="$(docker compose ps -q app)"
active_image=""
if [ -n "$app_container" ]; then
  active_image="$(docker inspect "$app_container" --format '{{.Config.Image}}')"
fi
if [[ "$active_image" =~ ^ksu-app:([0-9a-f]{40})$ ]]; then
  export KSU_IMAGE_TAG="${BASH_REMATCH[1]}"
else
  release_sha="$(git rev-parse HEAD)"
  if [[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] && docker image inspect "ksu-app:${release_sha}" >/dev/null 2>&1; then
    export KSU_IMAGE_TAG="$release_sha"
  else
    echo "Cannot resolve the active immutable ksu-app release tag; refusing to restart app as ksu-app:local." >&2
    exit 3
  fi
fi

echo "Restarting app with immutable release tag ${KSU_IMAGE_TAG}"
docker compose up -d --force-recreate app
sleep 5
curl -fsS "https://$DOMAIN/health/live"
echo
curl -fsS "https://api.telegram.org/bot$(grep ^BOT_TOKEN= .env | cut -d= -f2-)/getWebhookInfo" | sed -E "s/[0-9]{9,}:[A-Za-z0-9_-]+/[REDACTED]/g"
echo
