#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/womo-ai
REPO_URL=https://github.com/danielwauer-maker/womo-ai.git
NGINX_SITE=/etc/nginx/sites-available/womo-review
NGINX_ENABLED=/etc/nginx/sites-enabled/womo-review

if ! command -v git >/dev/null 2>&1; then
  echo "git fehlt" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker fehlt" >&2
  exit 1
fi
if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx fehlt" >&2
  exit 1
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" reset --hard origin/main
fi

mkdir -p "$APP_DIR/data"

cp "$APP_DIR/deploy/nginx-womo-review.conf" "$NGINX_SITE"
ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
nginx -t
systemctl reload nginx

cd "$APP_DIR"
docker compose -f docker-compose.review.yml up -d --build

for i in {1..20}; do
  if curl -fsS http://127.0.0.1:8092/health >/dev/null; then
    echo "Womo AI review is healthy on 127.0.0.1:8092"
    exit 0
  fi
  sleep 2
done

echo "Health check failed" >&2
docker compose -f docker-compose.review.yml logs --tail=100
exit 1
