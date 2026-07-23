# Вопросы для пары

Веб-приложение для двоих: партнёры по очереди отвечают на вопросы об отношениях,
система сравнивает ответы, начисляет очки, виртуальную валюту и достижения.

## Стек

- **Backend:** FastAPI (Python 3.11), SQLAlchemy, SQLite, WebSocket, JWT
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS

## Структура проекта

```
couple-questions-app/
├── backend/
│   ├── app/
│   │   ├── main.py                # точка входа FastAPI
│   │   ├── config.py               # настройки (.env)
│   │   ├── database.py             # SQLAlchemy engine/session
│   │   ├── models.py               # ORM-модели
│   │   ├── schemas.py              # Pydantic-схемы
│   │   ├── auth.py                 # JWT: создание/проверка токена
│   │   ├── crud.py                 # бизнес-логика (пары, вопросы, достижения)
│   │   ├── seed_data.py            # начальный набор вопросов и достижений
│   │   ├── websocket_manager.py    # менеджер WebSocket-комнат
│   │   └── routers/
│   │       ├── auth.py             # POST /auth/register, /auth/refresh
│   │       ├── couples.py          # создание/присоединение к паре
│   │       ├── questions.py        # оценка вопросов, топ, админ-CRUD
│   │       └── game.py             # /game/history + WebSocket /ws/{couple_id}
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                 # bootstraps auth и редиректит
    │   ├── couple/page.tsx          # создание/присоединение к паре
    │   ├── game/page.tsx            # основной игровой экран (WebSocket)
    │   └── history/page.tsx         # история сыгранных раундов
    ├── components/
    │   ├── QuestionCard.tsx
    │   ├── AnswerInput.tsx
    │   ├── ResultModal.tsx
    │   ├── RatingStars.tsx
    │   └── AchievementToast.tsx
    ├── lib/
    │   ├── api.ts                   # REST-клиент
    │   ├── auth.ts                  # работа с JWT в localStorage
    │   └── websocket.ts             # обёртка над WebSocket
    ├── types/index.ts
    ├── package.json
    └── .env.local.example
```

## Запуск backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # при необходимости отредактируйте JWT_SECRET_KEY

uvicorn app.main:app --reload --port 8000
```

При старте приложение само создаёт таблицы SQLite (`couple_questions.db`) и
засеивает базу начальными 30 вопросами и 4 достижениями (`seed_data.py`).

API будет доступно на `http://localhost:8000`, документация Swagger — на
`http://localhost:8000/docs`.

## Запуск frontend

```bash
cd frontend
npm install

cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

Приложение будет доступно на `http://localhost:3000`.

## Как проверить сценарий на два устройства

1. Откройте `http://localhost:3000` в одном браузере (или вкладке инкогнито) — это
   первый партнёр. Приложение автоматически зарегистрирует анонимного
   пользователя и предложит создать пару — нажмите «Создать код приглашения».
2. Откройте `http://localhost:3000` в другом браузере/вкладке инкогнито — второй
   партнёр. Введите полученный 6-значный код в форму «Присоединиться».
3. Оба клиента автоматически попадут на экран игры и подключатся к
   `/ws/{couple_id}` через WebSocket.
4. Любой из партнёров нажимает «Начать раунд» — сервер случайно выбирает вопрос
   и того, кто отвечает первым.
5. Партнёр, чья очередь, вводит ответ. Как только он отправлен, второму
   партнёру приходит уведомление `your_turn` по WebSocket.
6. После ответа второго партнёра оба одновременно видят результат раунда
   (`round_result`): оба ответа, совпадение, начисленные очки и монеты.
7. Каждый может оценить вопрос от 1 до 5 звёзд или пожаловаться на него.
8. Историю сыгранных раундов можно посмотреть на странице «История»
   (`/history`).

## Аутентификация

В приложении нет логина и пароля. При первом обращении фронтенд вызывает
`POST /auth/register`, backend создаёт анонимного пользователя и выдаёт JWT
(поля `user_id`, `couple_id`, `exp`). Токен сохраняется в `localStorage` и
подставляется в заголовок `Authorization: Bearer <token>` для всех
REST-запросов и как query-параметр `token` при подключении к WebSocket.
После создания/присоединения к паре токен перевыпускается, чтобы в нём
появился актуальный `couple_id`.

## Дальнейшие шаги (не входит в каркас)

- Переход с SQLite на PostgreSQL: замените `DATABASE_URL` в `.env` на
  `postgresql+psycopg2://...` и добавьте `psycopg2-binary` в
  `requirements.txt` — благодаря SQLAlchemy код моделей менять не придётся.
  Для контроля миграций стоит добавить Alembic.
- Полноценная админ-панель поверх уже готовых `/questions/admin/*`
  эндпоинтов.
- Push-уведомления, если партнёр офлайн (сейчас уведомление о ходе приходит
  только если оба клиента подключены к WebSocket).
