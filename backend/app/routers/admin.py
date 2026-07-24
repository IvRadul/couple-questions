from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.config import settings
from app import models, crud
from app.schemas import (
    AdminClaimRequest,
    PackUploadRequest,
    PackAdminOut,
    PackAdminDetailOut,
    PackRejectRequest,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: models.User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Требуются права администратора")


def _pack_admin_out(pack: models.QuestionPack, db: Session) -> PackAdminOut:
    question_count = db.query(models.Question).filter(models.Question.pack_id == pack.id).count()
    return PackAdminOut(
        id=pack.id,
        name=pack.name,
        description=pack.description,
        price_coins=pack.price_coins,
        is_default=pack.is_default,
        status=pack.status.value,
        is_active=pack.is_active,
        created_by_id=pack.created_by_id,
        rejection_reason=pack.rejection_reason,
        question_count=question_count,
    )


def _pack_admin_detail_out(pack: models.QuestionPack, db: Session) -> PackAdminDetailOut:
    base = _pack_admin_out(pack, db)
    questions = db.query(models.Question).filter(models.Question.pack_id == pack.id).all()
    return PackAdminDetailOut(**base.model_dump(), questions=questions)


@router.post("/claim", response_model=UserOut)
def claim_admin(
    payload: AdminClaimRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Выдаёт текущему (уже анонимно зарегистрированному) пользователю права
    администратора, если он знает секретный ключ из ADMIN_SECRET_KEY. Это
    заменяет полноценный админ-логин — отдельного пароля в приложении нет."""
    if not settings.admin_secret_key or payload.secret != settings.admin_secret_key:
        raise HTTPException(status_code=403, detail="Неверный секретный ключ")
    user.is_admin = True
    db.commit()
    db.refresh(user)
    return user


@router.get("/packs", response_model=List[PackAdminOut])
def list_all_packs(
    status: Optional[str] = Query(default=None, description="pending | approved | rejected"),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    query = db.query(models.QuestionPack)
    if status:
        try:
            query = query.filter(models.QuestionPack.status == models.PackStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный статус")
    packs = query.order_by(models.QuestionPack.id.desc()).all()
    return [_pack_admin_out(p, db) for p in packs]


@router.get("/packs/{pack_id}", response_model=PackAdminDetailOut)
def get_pack_detail(
    pack_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    return _pack_admin_detail_out(pack, db)


@router.post("/packs/upload", response_model=PackAdminOut)
def admin_upload_pack(
    payload: PackUploadRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Прямая загрузка пака администратором — сразу approved, без модерации."""
    _require_admin(user)
    try:
        crud.validate_pack_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pack = crud.create_pack_from_payload(
        db, payload, status=models.PackStatus.approved, created_by_id=user.id
    )
    return _pack_admin_out(pack, db)


@router.post("/packs/{pack_id}/approve", response_model=PackAdminOut)
def approve_pack(
    pack_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    pack.status = models.PackStatus.approved
    pack.rejection_reason = None
    db.commit()
    db.refresh(pack)
    return _pack_admin_out(pack, db)


@router.post("/packs/{pack_id}/reject", response_model=PackAdminOut)
def reject_pack(
    pack_id: int,
    payload: PackRejectRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    pack.status = models.PackStatus.rejected
    pack.rejection_reason = payload.reason
    db.commit()
    db.refresh(pack)
    return _pack_admin_out(pack, db)


@router.delete("/packs/{pack_id}")
def deactivate_pack(
    pack_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Мягко скрывает пак (например, approved-пак, который решили снять с
    витрины). История уже сыгранных раундов при этом не ломается."""
    _require_admin(user)
    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        raise HTTPException(status_code=404, detail="Пак не найден")
    pack.is_active = False
    db.commit()
    return {"status": "deactivated"}
