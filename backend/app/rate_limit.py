"""Простой in-memory rate limiter (фиксированное окно), без внешних
зависимостей. Годится только для ОДНОГО процесса backend — проект и так
не поддерживает несколько воркеров/реплик (см. раздел "Важное ограничение:
один экземпляр backend" в DEPLOY.md, там же причина: WebSocket-менеджер
тоже держит состояние в памяти одного процесса). Если это когда-нибудь
изменится — сюда тоже понадобится Redis или аналог вместо словаря."""

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.time()
        window_start = now - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.pop(0)
        if len(hits) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много попыток. Подождите немного и попробуйте снова.",
            )
        hits.append(now)


def client_ip(request: Request) -> str:
    # За nginx реальный IP приходит в X-Forwarded-For (см. --proxy-headers
    # в backend/Dockerfile и proxy_set_header X-Forwarded-For в nginx-шаблоне).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_login_limiter = RateLimiter(max_attempts=10, window_seconds=300)
_set_password_limiter = RateLimiter(max_attempts=10, window_seconds=300)
_admin_claim_limiter = RateLimiter(max_attempts=5, window_seconds=300)


def rate_limit_login(request: Request) -> None:
    _login_limiter.check(client_ip(request))


def rate_limit_set_password(request: Request) -> None:
    _set_password_limiter.check(client_ip(request))


def rate_limit_admin_claim(request: Request) -> None:
    _admin_claim_limiter.check(client_ip(request))
