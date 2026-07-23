from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, couple_id: Optional[str] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "couple_id": couple_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный или истёкший токен")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Отсутствует токен авторизации")

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def decode_token_for_ws(token: str, db: Session) -> Optional[models.User]:
    """Аналог get_current_user, но без HTTP-исключений — для WebSocket-хендшейка."""
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    user = db.query(models.User).filter(models.User.id == payload.get("sub")).first()
    return user
