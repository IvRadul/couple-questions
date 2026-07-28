#!/usr/bin/env bash
# Генерирует nginx/conf.d/app.conf из шаблона app.conf.template,
# подставляя домен из корневого .env (DOMAIN).
#
# Запускать из корня проекта: ./scripts/render-nginx-config.sh
# Перезапускать после каждого изменения DOMAIN в .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
TEMPLATE="$ROOT_DIR/nginx/conf.d/app.conf.template"
OUTPUT="$ROOT_DIR/nginx/conf.d/app.conf"

if [ ! -f "$ENV_FILE" ]; then
  echo "Не найден $ENV_FILE. Сначала: cp .env.production.example .env" >&2
  exit 1
fi

# Читаем DOMAIN как обычный текст (grep/cut), а не через `source .env` —
# так одна кривая кавычка или спецсимвол в комментарии в другом месте файла
# не сломает разбор всего файла как bash-скрипта.
get_env_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d'=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

DOMAIN="$(get_env_value DOMAIN)"

if [ -z "$DOMAIN" ]; then
  echo "В .env должен быть задан DOMAIN" >&2
  exit 1
fi

sed "s/__DOMAIN__/${DOMAIN}/g" "$TEMPLATE" > "$OUTPUT"

echo "Готово: $OUTPUT (DOMAIN=$DOMAIN)"
