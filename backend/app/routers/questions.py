from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models
from app.schemas import RateQuestionRequest, QuestionOut, QuestionAdminOut, QuestionCreate

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/rate")
def rate_question(
    payload: RateQuestionRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = db.query(models.Question).filter(models.Question.id == payload.question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Вопрос не найден")

    if not payload.is_report and payload.stars is None:
        raise HTTPException(status_code=400, detail="Укажите количество звёзд или отметьте жалобу")

    rating = models.Rating(
        question_id=question.id,
        user_id=user.id,
        round_id=payload.round_id,
        stars=payload.stars,
        is_report=payload.is_report,
    )
    db.add(rating)

    if payload.is_report:
        question.report_count += 1
    else:
        question.rating_sum += payload.stars
        question.rating_count += 1
        user.questions_rated_count += 1

    db.commit()
    return {"status": "ok"}


@router.get("/top", response_model=List[QuestionOut])
def top_questions(limit: int = 10, db: Session = Depends(get_db)):
    """Топ вопросов по среднему рейтингу (нужен минимум 1 оценка)."""
    questions = (
        db.query(models.Question)
        .filter(models.Question.rating_count > 0)
        .all()
    )
    questions.sort(key=lambda q: q.average_rating, reverse=True)
    return questions[:limit]


# ---------- "Админские" эндпоинты (защищены флагом is_admin, без отдельного UI) ----------

def _require_admin(user: models.User):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Требуются права администратора")


@router.get("/admin/all", response_model=List[QuestionAdminOut])
def admin_list_questions(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    return db.query(models.Question).all()


@router.post("/admin/create", response_model=QuestionAdminOut)
def admin_create_question(
    payload: QuestionCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)

    if payload.question_type == "choice" and len(payload.options) < 2:
        raise HTTPException(status_code=400, detail="Вопрос с вариантами должен иметь минимум 2 варианта")

    question = models.Question(
        text=payload.text,
        category=payload.category,
        question_type=models.QuestionType(payload.question_type),
        pack_id=payload.pack_id,
    )
    db.add(question)
    db.flush()

    for i, opt in enumerate(payload.options):
        db.add(models.QuestionOption(question_id=question.id, text=opt.text, sort_order=i))

    db.commit()
    db.refresh(question)
    return question


@router.put("/admin/{question_id}", response_model=QuestionAdminOut)
def admin_edit_question(
    question_id: int,
    payload: QuestionCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Вопрос не найден")

    question.text = payload.text
    question.category = payload.category
    question.question_type = models.QuestionType(payload.question_type)
    question.pack_id = payload.pack_id

    if payload.question_type == "choice":
        if len(payload.options) < 2:
            raise HTTPException(status_code=400, detail="Вопрос с вариантами должен иметь минимум 2 варианта")
        db.query(models.QuestionOption).filter(models.QuestionOption.question_id == question.id).delete()
        for i, opt in enumerate(payload.options):
            db.add(models.QuestionOption(question_id=question.id, text=opt.text, sort_order=i))

    db.commit()
    db.refresh(question)
    return question


@router.delete("/admin/{question_id}")
def admin_delete_question(
    question_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Вопрос не найден")
    # Мягкое удаление — просто деактивируем, чтобы не сломать историю прошедших раундов
    question.is_active = False
    db.commit()
    return {"status": "deactivated"}
