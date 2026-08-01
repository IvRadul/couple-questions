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

**Если страница вообще не грузится** (браузер показывает что-то вроде
`NS_ERROR_NET_RESET` / "не удаётся установить соединение", а не
HTTP-ошибку) и при этом `docker compose ... logs backend` показывает
только внутренние обращения к `/health` — проверьте `docker compose ...
ps`: если `nginx` работает намного дольше, чем `backend`/`frontend`
(например, после `up -d --build`, который пересоздал только их), значит
nginx ещё держит IP-адреса старых, уже не существующих контейнеров —
nginx резолвит `backend`/`frontend` при старте и без специального
`resolver`-механизма не переоткрывает DNS-запись на лету. Шаблон уже
использует `resolver 127.0.0.11` (встроенный DNS докера) и переменные в
`proxy_pass`, чтобы это не повторялось — но если у вас `nginx/conf.d/app.conf`
сгенерирован из более старой версии шаблона (без `resolver`), обновите его:

```bash
./scripts/render-nginx-config.sh
docker compose -f docker-compose.prod.yml restart nginx
```

(именно `restart`, не `-s reload` — nginx должен заново прочитать
`resolver`-конфигурацию и переоткрыть соединения с апстримами).

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

**Версия 5 → обязательное имя.** Схема не менялась — `display_name` был
nullable-колонкой в `users` с самого начала, просто раньше никогда не
заполнялся. Существующие пользователи при следующем визите просто попадут
на `/welcome` и укажут имя один раз.

Но если ваша БД уже была засеяна вопросами ДО этой версии (а значит, ещё
без `{username}` в тексте) — сам текст вопросов автоматически не
обновится: `seed_packs_and_questions()` сеет только пустую БД
(`if db.query(QuestionPack).count() > 0: return`). Чтобы обновить текст уже
существующих стартовых вопросов на новые шаблонизированные версии (id,
рейтинги и история раундов не трогаются — обновляется только колонка
`text`), один раз выполните:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/migrate_v5_question_text.py
```

Скрипт идемпотентен (можно смело перезапускать) и находит строки по
точному совпадению старого текста — свои/загруженные через админку паки
не трогает.

**Версия 6 → одновременные ответы.** Схема не менялась, но у `game_rounds.status`
поменялся набор допустимых значений: `waiting_answer`/`waiting_guess` (по
очереди) заменены на одно `in_progress` (оба отвечают сразу и независимо).
Если на момент деплоя в паре был реально незавершённый раунд — его
status в БД останется старым значением, которое новая версия приложения
не распознает, и любой запрос, задевающий эту строку, упадёт с ошибкой.
Раунды живут недолго, так что на практике это редкость, но для
подстраховки перед деплоем этой версии выполните:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/couple_questions.db \
  "UPDATE game_rounds SET status = 'in_progress' WHERE status IN ('waiting_answer', 'waiting_guess');"
```

(если строк с такими статусами не было — команда просто ничего не изменит).
Незавершённые на тот момент раунды после этого возобновятся как обычный
`in_progress` — партнёрам, возможно, придётся заново отправить свои ответы,
если один из них уже успел ответить по старой (последовательной) логике.

**Версия 7 → игровые сессии (несколько вопросов подряд).** Добавилась новая
таблица `game_sessions` (создаётся автоматически при старте — `create_all`
создаёт только отсутствующие таблицы) и два новых поля у уже существующей
`game_rounds` (`session_id`, `sequence_number`) — их `create_all` сам не
добавит, нужно вручную:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  sqlite3 /app/data/couple_questions.db <<'SQL'
ALTER TABLE game_rounds ADD COLUMN session_id INTEGER;
ALTER TABLE game_rounds ADD COLUMN sequence_number INTEGER;
SQL
```

Оба поля nullable, старые (уже завершённые) раунды прекрасно проживут с
`NULL` в них — миграция ничего не задевает и не ломает историю прошлых игр.
Если на момент деплоя был незавершённый раунд без привязки к сессии (из
версии 6) — он доиграется как обычно, просто не будет частью никакой
сессии (это нормально, `session_id` для него так и останется `NULL`).

**Версия 9 → история пар и переподключение.** Новая таблица
`couple_memberships` — создаётся автоматически (`create_all` создаёт
отсутствующие таблицы), никаких `ALTER TABLE` не требуется.

⚠️ **Важное ограничение:** история членства ведётся только с этой версии
вперёд. Пары, расформированные ДО деплоя версии 9, не появятся в «Прошлых
парах» — для них просто нет записей в `couple_memberships` (эта таблица не
существовала, когда они создавались/расформировывались). Задним числом это
не восстанавливается: раунды/переписка хранят только `couple_id`, а не то,
кто именно был участником на момент создания пары. Если для вас это
критично (много пользователей, которым важна история старых пар) — дайте
знать, можно написать разовый скрипт-бэкфилл, который восстановит
членства по данным из `game_rounds` (`answerer_id`/`guesser_id`) для пар, в
которых был хотя бы один сыгранный раунд — но для пар без единого раунда
восстановить участников уже нечем.

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
