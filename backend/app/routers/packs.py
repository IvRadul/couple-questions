from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, crud
from app.schemas import PackOut, PackUnlockResponse

router = APIRouter(prefix="/packs", tags=["packs"])


@router.get("", response_model=List[PackOut])
def list_packs(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    packs = db.query(models.QuestionPack).order_by(models.QuestionPack.sort_order).all()
    unlocked_ids = set(crud.get_unlocked_pack_ids(db, user.couple_id)) if user.couple_id else set()

    result = []
    for pack in packs:
        question_count = (
            db.query(models.Question)
            .filter(models.Question.pack_id == pack.id, models.Question.is_active.is_(True))
            .count()
        )
        result.append(
            PackOut(
                id=pack.id,
                name=pack.name,
                description=pack.description,
                price_coins=pack.price_coins,
                is_default=pack.is_default,
                question_count=question_count,
                unlocked=pack.is_default or pack.id in unlocked_ids,
            )
        )
    return result


@router.post("/{pack_id}/unlock", response_model=PackUnlockResponse)
def unlock_pack(
    pack_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.couple_id:
        raise HTTPException(status_code=400, detail="Вы не состоите в паре")
    try:
        crud.unlock_pack(db, user, pack_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PackUnlockResponse(pack_id=pack_id, remaining_coins=user.coins)
