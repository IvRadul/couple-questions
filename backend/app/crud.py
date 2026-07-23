import random
import re
import string
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app import models


# ---------- Users ----------

def create_user(db: Session) -> models.User:
    user = models.User()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


# ---------- Couples ----------

def _generate_invite_code(db: Session) -> str:
    while True:
        code = "".join(random.choices(string.digits, k=6))
        exists = db.query(models.Couple).filter(models.Couple.invite_code == code).first()
        if not exists:
            return code


def create_couple(db: Session, creator: models.User) -> models.Couple:
    couple = models.Couple(invite_code=_generate_invite_code(db), status=models.CoupleStatus.pending)
    db.add(couple)
    db.commit()
    db.refresh(couple)

    creator.couple_id = couple.id
    db.commit()
    return couple


def join_couple(db: Session, user: models.User, invite_code: str) -> models.Couple:
    couple = db.query(models.Couple).filter(models.Couple.invite_code == invite_code).first()
    if couple is None:
        raise ValueError("Пара с таким кодом не найдена")
    if couple.status == models.CoupleStatus.active:
        raise ValueError("В этой паре уже два участника")

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if any(m.id == user.id for m in members):
        raise ValueError("Вы уже состоите в этой паре")

    user.couple_id = couple.id
    couple.status = models.CoupleStatus.active
    db.commit()
    db.refresh(couple)
    return couple


# ---------- Questions ----------

def pick_random_question(db: Session, couple_id: str) -> Optional[models.Question]:
    played_ids = [
        row[0]
        for row in db.query(models.CoupleQuestionHistory.question_id)
        .filter(models.CoupleQuestionHistory.couple_id == couple_id)
        .all()
    ]
    query = db.query(models.Question).filter(models.Question.is_active.is_(True))
    if played_ids:
        query = query.filter(~models.Question.id.in_(played_ids))

    candidates = query.all()
    if not candidates:
        return None
    return random.choice(candidates)


def normalize_answer(text: str) -> str:
    """Нормализация для нечёткого сравнения ответов: нижний регистр,
    убираем пунктуацию/лишние пробелы."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text


def answers_match(text_a: str, text_b: str) -> bool:
    return normalize_answer(text_a) == normalize_answer(text_b)


# ---------- Achievements ----------

ACHIEVEMENT_SEED = [
    {
        "code": "first_game",
        "title": "Первая игра",
        "description": "Сыграйте свой первый раунд",
        "coin_reward": 10,
    },
    {
        "code": "streak_10",
        "title": "10 совпадений подряд",
        "description": "Совпадите с партнёром 10 раз подряд",
        "coin_reward": 50,
    },
    {
        "code": "fast_answer",
        "title": "Молниеносный ответ",
        "description": "Ответьте на вопрос за 10 секунд или быстрее",
        "coin_reward": 15,
    },
    {
        "code": "rated_50",
        "title": "Придирчивый критик",
        "description": "Оцените 50 вопросов",
        "coin_reward": 30,
    },
]


def seed_achievements(db: Session) -> None:
    for item in ACHIEVEMENT_SEED:
        exists = db.query(models.Achievement).filter(models.Achievement.code == item["code"]).first()
        if not exists:
            db.add(models.Achievement(**item))
    db.commit()


def grant_achievement(db: Session, user: models.User, code: str) -> Optional[models.Achievement]:
    achievement = db.query(models.Achievement).filter(models.Achievement.code == code).first()
    if achievement is None:
        return None

    already = (
        db.query(models.UserAchievement)
        .filter(
            models.UserAchievement.user_id == user.id,
            models.UserAchievement.achievement_id == achievement.id,
        )
        .first()
    )
    if already:
        return None

    db.add(models.UserAchievement(user_id=user.id, achievement_id=achievement.id))
    user.coins += achievement.coin_reward
    db.commit()
    return achievement


def check_achievements_after_round(
    db: Session, user: models.User, response_time_seconds: Optional[int]
) -> List[models.Achievement]:
    """Проверяет условия достижений после того, как раунд для пользователя завершён,
    и возвращает список только что полученных достижений."""
    newly_earned = []

    if user.total_games == 1:
        got = grant_achievement(db, user, "first_game")
        if got:
            newly_earned.append(got)

    if user.best_match_streak >= 10:
        got = grant_achievement(db, user, "streak_10")
        if got:
            newly_earned.append(got)

    if response_time_seconds is not None and response_time_seconds <= 10:
        got = grant_achievement(db, user, "fast_answer")
        if got:
            newly_earned.append(got)

    if user.questions_rated_count >= 50:
        got = grant_achievement(db, user, "rated_50")
        if got:
            newly_earned.append(got)

    return newly_earned
