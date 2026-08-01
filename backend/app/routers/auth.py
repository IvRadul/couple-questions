from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud, models
from app.auth import create_access_token, get_current_user
from app.schemas import TokenResponse, SetPasswordRequest, LoginRequest, UserOut
from app.rate_limit import rate_limit_login, rate_limit_set_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(db: Session = Depends(get_db)):
    """Создаёт нового анонимного пользователя и выдаёт JWT.
    Фронтенд вызывает это один раз при первом визите и сохраняет токен в
    localStorage — логин/пароль на этом этапе не нужны. Пользователь может
    позже закрепить аккаунт логином/паролем через /auth/set-password, чтобы
    не потерять прогресс при смене устройства/браузера."""
    user = crud.create_user(db)
    token = create_access_token(user_id=user.id, couple_id=user.couple_id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=user.couple_id)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(user=Depends(get_current_user)):
    """Перевыпускает токен с актуальным couple_id
    (полезно сразу после создания/присоединения к паре)."""
    token = create_access_token(user_id=user.id, couple_id=user.couple_id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=user.couple_id)


@router.post("/set-password", response_model=UserOut)
def set_password(
    payload: SetPasswordRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limit_set_password),
):
    """Закрепляет логин/пароль за ТЕКУЩИМ (уже существующим, в т.ч. анонимным)
    аккаунтом — не создаёт новый и не трогает прогресс/пару. После этого
    можно входить в тот же аккаунт с другого устройства через /auth/login."""
    try:
        updated = crud.set_user_credentials(db, user, payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return updated


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db), _rl: None = Depends(rate_limit_login)):
    """Вход по логину/паролю в ранее закреплённый аккаунт (см. /auth/set-password).
    Выдаёт новый JWT для этого пользователя — прогресс, монеты, пара (если
    есть) подтягиваются автоматически."""
    user = crud.authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_access_token(user_id=user.id, couple_id=user.couple_id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=user.couple_id)
