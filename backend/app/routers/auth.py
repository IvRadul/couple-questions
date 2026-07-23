from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud
from app.auth import create_access_token, get_current_user
from app.schemas import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(db: Session = Depends(get_db)):
    """Создаёт нового анонимного пользователя и выдаёт JWT.
    Логина/пароля нет — фронтенд вызывает этот эндпоинт один раз
    и сохраняет токен в localStorage."""
    user = crud.create_user(db)
    token = create_access_token(user_id=user.id, couple_id=user.couple_id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=user.couple_id)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(user=Depends(get_current_user)):
    """Перевыпускает токен с актуальным couple_id
    (полезно сразу после создания/присоединения к паре)."""
    token = create_access_token(user_id=user.id, couple_id=user.couple_id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=user.couple_id)
