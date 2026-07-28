# Выкладка на VDS

Пошаговая инструкция по развёртыванию на чистом VDS с собственным доменом,
HTTPS через Let's Encrypt, и базовой защитой сервера.

Архитектура: **один домен**, роутинг по путям через nginx —
`/` → фронтенд, `/api/` и `/api/ws/`/`/ws/` → backend (REST и WebSocket).
Никаких поддоменов заводить не нужно.

## 0. Что понадобится

- VDS с публичным IP (2 GB RAM хватает с запасом; 1 GB — впритык, но должно
  работать — стек лёгкий).
- Домен (или поддомен), на который вы можете добавить DNS-записи.
- A-запись, указывающая на IP сервера (и опционально та же запись для
  `www.` — шаблон nginx включает оба варианта в один сертификат).

## 1. Подготовка сервера

Подключитесь по SSH и установите Docker:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# перелогиньтесь (exit и зайдите по SSH заново), чтобы группа применилась
```

Проверьте, что `docker compose` (v2, через пробел, не `docker-compose`)
доступен:

```bash
docker compose version
```

Настройте firewall — открываем только SSH, HTTP и HTTPS:

```bash
sudo apt-get update && sudo apt-get install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Порты 3000 и 8000 наружу открывать не нужно — backend и frontend в
`docker-compose.prod.yml` не пробрасываются на хост вообще, наружу торчит
только nginx на 80/443.

## 2. DNS

Создайте A-запись у вашего DNS-провайдера:

| Тип | Имя               | Значение          |
|-----|--------------------|--------------------|
| A   | example.com        | IP вашего VDS      |
| A   | www.example.com    | IP вашего VDS      |

Дождитесь, пока запись разойдётся (`dig example.com` должен возвращать IP
сервера) — без этого Let's Encrypt не сможет подтвердить владение доменом.

## 3. Код на сервере

```bash
git clone <ваш форк/репозиторий> couple-questions-app
# либо просто распакуйте архив проекта
cd couple-questions-app
```

## 4. Настройка окружения

```bash
cp .env.production.example .env
cp backend/.env.example backend/.env
```

Отредактируйте `.env` (корень проекта):
- `DOMAIN` — ваш реальный домен (без `https://`, без `www.`);
- `LETSENCRYPT_EMAIL` — ваш email;
- `NEXT_PUBLIC_API_URL=https://example.com/api` — **обязательно с `/api`**
  на конце (см. комментарий в файле — так работает роутинг в nginx).

Отредактируйте `backend/.env`:
- `JWT_SECRET_KEY` — сгенерируйте случайную строку:
  `openssl rand -hex 32`;
- `ADMIN_SECRET_KEY` — то же самое, отдельным значением:
  `openssl rand -hex 32`;
- `CORS_ORIGINS=https://example.com` (ваш домен, со схемой `https://`, без
  слэша на конце).

Сохраните оба сгенерированных секрета в надёжном месте (менеджер паролей) —
`ADMIN_SECRET_KEY` — это единственный способ получить права администратора
в приложении.

## 5. Сгенерировать nginx-конфиг и получить сертификат

```bash
./scripts/render-nginx-config.sh
./init-letsencrypt.sh
```

`init-letsencrypt.sh` поднимет nginx с временным самоподписанным
сертификатом, запросит настоящий сертификат Let's Encrypt для `DOMAIN` и
`www.DOMAIN`, перезагрузит nginx и запустит весь стек. Требует, чтобы порт
80 был свободен и DNS уже указывал на сервер (см. шаг 2) — если скрипт
падает с ошибкой валидации домена, скорее всего DNS ещё не разошёлся,
подождите и попробуйте снова. Если сертификат для домена уже существует
(например, вы перезапускаете скрипт повторно), выпуск нового пропускается
автоматически.

Если `www.DOMAIN` вам не нужен — уберите его из `-d` в `init-letsencrypt.sh`
и из `server_name` в `nginx/conf.d/app.conf.template` перед запуском.

## 6. Проверка

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

Откройте `https://example.com` — должно открыться приложение с валидным
замком браузера. Обязательно проверьте не только обычные REST-действия
(создание пары, паки), но и сам раунд игры — именно WebSocket-соединение
(`/api/ws/...`) чаще всего страдает при ошибках в nginx-роутинге. Если
раунд не запускается или зависает на "Подключение..." — почти наверняка
дело в путях `/api/ws/` в `nginx/conf.d/app.conf` (см. пояснение в
шаблоне) или в несовпадении `NEXT_PUBLIC_API_URL` с реальным доменом.

**Про CORS и www.** Канонический домен — без `www` (`DOMAIN` из `.env`).
`www.DOMAIN` везде только 301-редиректит на него — специально, чтобы
браузер никогда не грузил приложение с `www`, пока фронтенд обращается к
API на голом домене (или наоборот): это два разных origin, и браузер
блокирует такие запросы как cross-origin (CORS), даже если backend вообще
не участвует в проблеме. Если после обновления `app.conf` ошибки CORS
всё ещё есть:
- убедитесь, что `nginx/conf.d/app.conf` перегенерирован
  (`./scripts/render-nginx-config.sh`) и nginx перезапущен/перезагружен
  (`docker compose -f docker-compose.prod.yml exec nginx nginx -s reload`);
- проверьте в адресной строке браузера, что вы реально на `https://example.com`,
  а не на `https://www.example.com` (жёстко обновите страницу — Ctrl+Shift+R
  — старая версия могла закэшироваться);
- убедитесь, что `NEXT_PUBLIC_API_URL` и `CORS_ORIGINS` (в `backend/.env`)
  оба указывают на один и тот же канонический домен без `www`;
- если правили `backend/.env` — простого сохранения файла недостаточно,
  контейнер читает `.env` только при старте: перезапустите backend
  (`docker compose -f docker-compose.prod.yml up -d backend`, пересборка не
  нужна, т.к. `.env` не копируется в образ, а подключается через `env_file`).

Зайдите на `https://example.com/admin` и получите права администратора
вашим `ADMIN_SECRET_KEY`.

## 7. Автопродление сертификата

Уже настроено: сервис `certbot` в `docker-compose.prod.yml` — это
бесконечный цикл, который каждые 12 часов проверяет срок и продлевает
сертификат через уже работающий webroot-механизм. Отдельный cron не нужен,
достаточно, чтобы контейнер `certbot` работал постоянно
(`restart: unless-stopped`).

## 8. Резервное копирование данных

По умолчанию все данные (пользователи, пары, паки, история) лежат в SQLite
внутри volume `backend_data`. Команды ниже используют CLI-утилиту `sqlite3`
внутри backend-контейнера (не путать со встроенным Python-модулем
`sqlite3` — это разные вещи). Если вы разворачивались до того, как эта
утилита попала в `backend/Dockerfile`, пересоберите образ один раз:
`docker compose -f docker-compose.prod.yml up -d --build backend`.

Бэкап одной командой:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/couple_questions.db ".backup /app/data/backup-$(date +%F).db"
docker cp "$(docker compose -f docker-compose.prod.yml ps -q backend)":/app/data/backup-$(date +%F).db ./
```

Повесьте это на cron (например, ежедневно ночью) и храните копии за
пределами сервера (S3, другой сервер и т.п.).

## 9. Обновление после изменений в коде

```bash
git pull   # или обновите файлы иначе
docker compose -f docker-compose.prod.yml up -d --build
```

Если менялась схема БД (новые таблицы/колонки) — миграций в проекте нет
(SQLAlchemy создаёт таблицы `create_all` только при первом запуске на пустой
БД), так что после структурных изменений моделей нужно либо вручную
накатить `ALTER TABLE`, либо (для тестового/некритичного окружения) удалить
volume `backend_data` и начать с чистой БД. Для реального продакшена стоит
добавить Alembic — сейчас в проекте этого нет.

Ниже — накопленные вручную миграции по версиям (применяйте по порядку, если
апгрейдитесь с более старой версии; если БД уже актуальна — соответствующий
`ALTER TABLE` просто упадёт с "duplicate column", это нормально, значит уже
накатили).

**Версия 3 → модерация паков** (добавляет `status`, `is_active`,
`created_by_id`, `rejection_reason` в `question_packs`):

```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/couple_questions.db <<'SQL'
ALTER TABLE question_packs ADD COLUMN status VARCHAR NOT NULL DEFAULT 'approved';
ALTER TABLE question_packs ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE question_packs ADD COLUMN created_by_id VARCHAR;
ALTER TABLE question_packs ADD COLUMN rejection_reason VARCHAR(256);
SQL
```

**Версия 4 → логин/пароль** (добавляет `username` и `password_hash` в уже
существующую таблицу `users`, без потери данных):

```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/couple_questions.db <<'SQL'
ALTER TABLE users ADD COLUMN username VARCHAR(32);
ALTER TABLE users ADD COLUMN password_hash VARCHAR;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username);
SQL
```

Сделайте бэкап (см. шаг 8) перед этим на всякий случай. Новые колонки
nullable, так что у уже существующих пользователей `username` останется
`NULL` (аккаунт остаётся анонимным, как и был) — ничего не сломается, пока
они сами не зайдут на `/account` и не зададут логин.

**Версия 5 → обязательное имя.** Миграция не нужна — `display_name` был
nullable-колонкой в `users` с самого начала, просто раньше никогда не
заполнялся. Существующие пользователи при следующем визите просто попадут
на `/welcome` и укажут имя один раз.

## 10. Важное ограничение: один экземпляр backend

`websocket_manager.py` хранит активные WebSocket-соединения в памяти одного
процесса (`ConnectionManager`). Это значит:

- **Нельзя** запускать несколько реплик backend (`docker compose up --scale
  backend=2`) и **нельзя** добавлять uvicorn `--workers > 1` — сообщение,
  отправленное одним воркером, не долетит до партнёра, чей сокет держит
  другой воркер. Раунды будут "зависать" непредсказуемо.
- Для вертикального масштабирования (что обычно и нужно на одном VDS) это
  не проблема — просто не увеличивайте число воркеров/реплик backend.
- Если в будущем понадобится горизонтальное масштабирование — нужен Redis
  (или аналог) как shared pub/sub между воркерами вместо in-memory
  `ConnectionManager`. Это отдельная задача, в текущей версии не
  реализована.

По той же причине SQLite тоже нормально работает только с одним
backend-процессом, пишущим в файл — что и обеспечивается ограничением выше.

## Итоговая структура продакшен-файлов

```
couple-questions-app/
├── docker-compose.yml            # локальная разработка (без nginx/TLS)
├── docker-compose.prod.yml       # прод: backend + frontend + nginx + certbot
├── .env.production.example       # шаблон корневого .env для прода
├── init-letsencrypt.sh           # первичный выпуск TLS-сертификата
├── scripts/
│   └── render-nginx-config.sh    # подставляет DOMAIN в nginx-конфиг
└── nginx/
    ├── nginx.conf                # базовый http-блок (общий, без домена)
    └── conf.d/
        └── app.conf.template     # шаблон роутинга (домен — плейсхолдер)
```

`nginx/conf.d/app.conf` (сгенерированный, с реальным доменом) и данные
certbot (именованные volume'ы `certbot-www`/`certbot-conf`) в git не
попадают.
