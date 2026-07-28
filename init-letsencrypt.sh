#!/usr/bin/env bash
# Первичный выпуск сертификата Let's Encrypt для DOMAIN (+ www.DOMAIN) из
# корневого .env. Запускать ОДИН РАЗ на сервере перед первым стартом
# продакшен-стека (см. DEPLOY.md). Требует, чтобы порт 80 был свободен и
# домен уже указывал (A-записью) на этот сервер.
#
# Работает через уже описанный в docker-compose.prod.yml сервис certbot и
# именованные volume'ы (certbot-www/certbot-conf) — никаких host-путей,
# всё выполняется внутри контейнеров, поэтому годится и для bind-mount,
# и для named-volume раскладки.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="docker compose -f docker-compose.prod.yml"
RSA_KEY_SIZE=4096

if [ ! -f .env ]; then
  echo "Не найден .env в корне проекта. Сначала: cp .env.production.example .env и заполните его." >&2
  exit 1
fi

# Читаем значения как обычный текст (grep/cut), а не через `source .env` —
# так одна кривая кавычка или спецсимвол в комментарии в другом месте файла
# не сломает разбор всего файла как bash-скрипта (см. DEPLOY.md).
get_env_value() {
  local key="$1"
  grep -E "^${key}=" .env | tail -n1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

DOMAIN="$(get_env_value DOMAIN)"
LETSENCRYPT_EMAIL="$(get_env_value LETSENCRYPT_EMAIL)"

if [ -z "$DOMAIN" ] || [ -z "$LETSENCRYPT_EMAIL" ]; then
  echo "В .env должны быть заданы DOMAIN и LETSENCRYPT_EMAIL" >&2
  exit 1
fi

if [ ! -f "./nginx/conf.d/app.conf" ]; then
  echo "Не найден nginx/conf.d/app.conf — сначала выполните ./scripts/render-nginx-config.sh" >&2
  exit 1
fi

if ! command -v docker &> /dev/null; then
  echo "Docker не найден — установите Docker и docker compose перед продолжением." >&2
  exit 1
fi

cert_exists() {
  $COMPOSE run --rm --entrypoint sh certbot -c "[ -d /etc/letsencrypt/live/$DOMAIN ]" > /dev/null 2>&1
}

if cert_exists; then
  echo "### Сертификат для $DOMAIN уже существует — пропускаем выпуск, сразу поднимаем стек."
else
  echo "### Создаём временный self-signed сертификат для $DOMAIN (чтобы nginx смог стартовать) ..."
  $COMPOSE run --rm --entrypoint sh certbot -c "
    mkdir -p /etc/letsencrypt/live/$DOMAIN &&
    openssl req -x509 -nodes -newkey rsa:$RSA_KEY_SIZE -days 1 \
      -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
      -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
      -subj '/CN=localhost'
  "

  echo "### Запускаем nginx с временным сертификатом ..."
  $COMPOSE up -d nginx

  echo "### Удаляем временный сертификат, чтобы получить настоящий ..."
  $COMPOSE run --rm --entrypoint sh certbot -c "
    rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf
  "

  echo "### Запрашиваем настоящий сертификат Let's Encrypt для $DOMAIN и www.$DOMAIN ..."
  $COMPOSE run --rm --entrypoint sh certbot -c "
    certbot certonly --webroot -w /var/www/certbot \
      --email '$LETSENCRYPT_EMAIL' \
      -d '$DOMAIN' -d 'www.$DOMAIN' \
      --rsa-key-size $RSA_KEY_SIZE \
      --agree-tos \
      --non-interactive
  "
fi

echo "### Запускаем весь стек ..."
$COMPOSE up -d --build

echo "### Перезагружаем nginx с настоящим сертификатом ..."
$COMPOSE exec nginx nginx -s reload

echo "### Готово. Автопродление уже настроено — за него отвечает сервис 'certbot' (renew-цикл каждые 12ч)."
echo "### Если 'www.$DOMAIN' вам не нужен — уберите его из -d выше и из server_name в nginx/conf.d/app.conf.template."
