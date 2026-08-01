from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, create_access_token
from app import crud, models
from app.schemas import CoupleCreateResponse, CoupleJoinRequest, CoupleOut, TokenResponse, CoupleHistoryItemOut
from app.websocket_manager import manager

router = APIRouter(prefix="/couples", tags=["couples"])


@router.post("/create", response_model=CoupleCreateResponse)
def create_couple(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.couple_id:
        # Пользователь уже создавал пару (например, повторный клик или
        # повторный вызов эффекта на фронтенде) — не считаем это ошибкой,
        # просто возвращаем данные существующей пары с актуальным токеном.
        existing = db.query(models.Couple).filter(models.Couple.id == user.couple_id).first()
        token = create_access_token(user_id=user.id, couple_id=existing.id)
        return CoupleCreateResponse(
            couple_id=existing.id,
            invite_code=existing.invite_code,
            status=existing.status.value,
            access_token=token,
        )

    couple = crud.create_couple(db, user)
    token = create_access_token(user_id=user.id, couple_id=couple.id)
    return CoupleCreateResponse(
        couple_id=couple.id, invite_code=couple.invite_code, status=couple.status.value, access_token=token
    )


@router.post("/join", response_model=TokenResponse)
def join_couple(
    payload: CoupleJoinRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.couple_id:
        existing = db.query(models.Couple).filter(models.Couple.id == user.couple_id).first()
        if existing and existing.invite_code == payload.invite_code:
            # Повторный вызов join для той же пары (двойной клик и т.п.) — не ошибка.
            token = create_access_token(user_id=user.id, couple_id=existing.id)
            return TokenResponse(access_token=token, user_id=user.id, couple_id=existing.id)
        raise HTTPException(status_code=400, detail="Вы уже состоите в другой паре")

    try:
        couple = crud.join_couple(db, user, payload.invite_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Перевыпускаем токен, чтобы couple_id сразу попал в JWT
    token = create_access_token(user_id=user.id, couple_id=couple.id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=couple.id)


@router.post("/leave", response_model=TokenResponse)
async def leave_couple(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Расформировывает текущую пару. Монеты, достижения и статистика
    пользователя сохраняются — после этого можно создать новую пару
    или присоединиться к чужому коду."""
    old_couple_id = user.couple_id
    try:
        crud.leave_couple(db, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if old_couple_id:
        # Партнёр может быть прямо сейчас подключён к WebSocket этой пары
        # (например, посреди игры) — сообщаем ему явно, вместо того чтобы
        # он просто наткнулся на ошибки при следующем действии.
        await manager.broadcast_to_couple(old_couple_id, {"action": "couple_disbanded"})

    token = create_access_token(user_id=user.id, couple_id=None)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=None)


@router.get("/me", response_model=CoupleOut)
def get_my_couple(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.couple_id:
        raise HTTPException(status_code=404, detail="Вы пока не состоите в паре")
    couple = db.query(models.Couple).filter(models.Couple.id == user.couple_id).first()
    return couple


@router.get("/history", response_model=List[CoupleHistoryItemOut])
def get_couple_history(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Пары, в которых пользователь когда-либо состоял, кроме текущей."""
    return crud.get_couple_history(db, user)


@router.post("/{couple_id}/reconnect", response_model=TokenResponse)
def reconnect_couple(
    couple_id: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Переподключение к паре, в которой пользователь состоял раньше.
    Симметрично обычному join: если партнёр ещё не переподключился —
    пара остаётся в статусе pending, пока не переподключятся оба."""
    try:
        couple = crud.reconnect_couple(db, user, couple_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token(user_id=user.id, couple_id=couple.id)
    return TokenResponse(access_token=token, user_id=user.id, couple_id=couple.id)
