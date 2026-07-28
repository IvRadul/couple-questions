FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Системные зависимости: build-essential — для сборки некоторых Python-пакетов
# (например, cryptography); sqlite3 — CLI-утилита для бэкапов и ручных
# ALTER TABLE миграций (см. DEPLOY.md), отдельно от Python-модуля sqlite3,
# который уже встроен в сам интерпретатор.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Каталог для файла SQLite — монтируется как volume в docker-compose,
# чтобы данные переживали пересборку контейнера.
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
