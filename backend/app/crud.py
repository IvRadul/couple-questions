import random
import re
import string
from typing import Optional, List

from sqlalchemy import false as sa_false, func
from sqlalchemy.orm import Session

from app import models
from app.auth import hash_password, verify_password


# ---------- Users ----------

def create_user(db: Session) -> models.User:
    user = models.User()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


DISPLAY_NAME_MAX_LENGTH = 32


def set_display_name(db: Session, user: models.User, display_name: str) -> models.User:
    """Устанавливает отображаемое имя пользователя. В отличие от username
    (логина для входа), это имя не уникально и не требует пароля — оно
    обязательно для игры и подставляется в текст вопросов вместо
    статичного "партнёр" (см. render_question_text)."""
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Имя не может быть пустым")
    if len(display_name) > DISPLAY_NAME_MAX_LENGTH:
        raise ValueError(f"Имя не длиннее {DISPLAY_NAME_MAX_LENGTH} символов")

    user.display_name = display_name
    db.commit()
    db.refresh(user)
    return user


def render_question_text(text: str, display_name: Optional[str]) -> str:
    """Подставляет имя в шаблон вопроса вида '...{username}...'.
    Если по какой-то причине имя не задано (не должно происходить, раз имя
    обязательно), подставляется нейтральное "партнёр"."""
    return text.replace("{username}", display_name or "партнёр")


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def _get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()


def set_user_credentials(db: Session, user: models.User, username: str, password: str) -> models.User:
    """Закрепляет логин/пароль за уже существующим (в т.ч. анонимным)
    пользователем, чтобы он мог войти с другого устройства без потери
    прогресса. Не создаёт нового пользователя и не трогает couple_id/монеты."""
    username = username.strip()

    if not USERNAME_RE.match(username):
        raise ValueError("Логин: 3-32 символа, латиница/цифры/подчёркивание")
    if len(password) < 6:
        raise ValueError("Пароль должен быть не короче 6 символов")

    existing = _get_user_by_username(db, username)
    if existing is not None and existing.id != user.id:
        raise ValueError("Этот логин уже занят")

    user.username = username
    user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = _get_user_by_username(db, username.strip())
    if user is None or user.password_hash is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


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
    if couple.status == models.CoupleStatus.disbanded:
        raise ValueError("Эта пара больше не активна")

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if any(m.id == user.id for m in members):
        raise ValueError("Вы уже состоите в этой паре")

    user.couple_id = couple.id
    couple.status = models.CoupleStatus.active
    db.commit()
    db.refresh(couple)
    return couple


def leave_couple(db: Session, user: models.User) -> None:
    """Расформировывает текущую пару пользователя. Прогресс (монеты,
    достижения, статистика) остаётся на пользователях — расформировывается
    только связь между ними, история старой пары (раунды, пройденные
    вопросы, открытые паки) в БД сохраняется как есть."""
    if not user.couple_id:
        raise ValueError("Вы не состоите в паре")

    couple = db.query(models.Couple).filter(models.Couple.id == user.couple_id).first()
    if couple is None:
        user.couple_id = None
        db.commit()
        return

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    for member in members:
        member.couple_id = None
    couple.status = models.CoupleStatus.disbanded
    db.commit()


# ---------- Question packs ----------

def get_unlocked_pack_ids(db: Session, couple_id: str) -> List[int]:
    """Только паки, которые прошли модерацию (status == approved) и не скрыты
    администратором (is_active == True) — либо бесплатные по умолчанию, либо
    явно открытые этой парой за монеты."""
    approved_active = (
        models.QuestionPack.status == models.PackStatus.approved,
        models.QuestionPack.is_active.is_(True),
    )
    default_ids = [
        row[0]
        for row in db.query(models.QuestionPack.id)
        .filter(models.QuestionPack.is_default.is_(True), *approved_active)
        .all()
    ]
    unlocked_ids = [
        row[0]
        for row in db.query(models.CouplePackUnlock.pack_id)
        .join(models.QuestionPack, models.QuestionPack.id == models.CouplePackUnlock.pack_id)
        .filter(models.CouplePackUnlock.couple_id == couple_id, *approved_active)
        .all()
    ]
    return list(set(default_ids) | set(unlocked_ids))


def unlock_pack(db: Session, user: models.User, pack_id: int) -> models.CouplePackUnlock:
    if not user.couple_id:
        raise ValueError("Вы не состоите в паре")

    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        raise ValueError("Пак не найден")
    if pack.status != models.PackStatus.approved or not pack.is_active:
        raise ValueError("Этот пак сейчас недоступен")
    if pack.is_default:
        raise ValueError("Этот пак уже доступен бесплатно")

    already = (
        db.query(models.CouplePackUnlock)
        .filter(
            models.CouplePackUnlock.couple_id == user.couple_id,
            models.CouplePackUnlock.pack_id == pack_id,
        )
        .first()
    )
    if already:
        raise ValueError("Этот пак уже открыт")

    if user.coins < pack.price_coins:
        raise ValueError("Недостаточно монет")

    user.coins -= pack.price_coins
    unlock = models.CouplePackUnlock(couple_id=user.couple_id, pack_id=pack_id, unlocked_by_id=user.id)
    db.add(unlock)
    db.commit()
    db.refresh(unlock)
    return unlock


def validate_pack_payload(payload) -> None:
    """Общая проверка структуры пака при загрузке админом или отправке
    пользователем на модерацию. Бросает ValueError с понятным сообщением."""
    if not payload.name or not payload.name.strip():
        raise ValueError("Название пака не может быть пустым")
    if payload.price_coins < 0:
        raise ValueError("Цена пака не может быть отрицательной")
    if not payload.questions:
        raise ValueError("Пак должен содержать хотя бы один вопрос")

    for q in payload.questions:
        if not q.text or not q.text.strip():
            raise ValueError("Текст вопроса не может быть пустым")
        if q.question_type not in ("open", "choice"):
            raise ValueError(f"Неизвестный тип вопроса: {q.question_type!r} (допустимо: open, choice)")
        if q.question_type == "choice":
            texts = [o.text.strip() for o in q.options if o.text and o.text.strip()]
            if len(texts) < 2:
                raise ValueError(f"Вопрос «{q.text}» типа choice должен содержать минимум 2 варианта ответа")
            if len(set(texts)) != len(texts):
                raise ValueError(f"Вопрос «{q.text}» содержит повторяющиеся варианты ответа")


def create_pack_from_payload(
    db: Session,
    payload,
    status: models.PackStatus,
    created_by_id: Optional[str] = None,
    is_default: bool = False,
) -> models.QuestionPack:
    pack = models.QuestionPack(
        name=payload.name.strip(),
        description=(payload.description or None),
        price_coins=payload.price_coins,
        is_default=is_default,
        status=status,
        created_by_id=created_by_id,
    )
    db.add(pack)
    db.flush()  # получаем pack.id до commit

    for q in payload.questions:
        question = models.Question(
            text=q.text.strip(),
            category=(q.category or "general").strip() or "general",
            question_type=models.QuestionType(q.question_type),
            pack_id=pack.id,
        )
        db.add(question)
        db.flush()
        if q.question_type == "choice":
            for i, opt in enumerate(q.options):
                if opt.text and opt.text.strip():
                    db.add(models.QuestionOption(question_id=question.id, text=opt.text.strip(), sort_order=i))

    db.commit()
    db.refresh(pack)
    return pack


# ---------- Questions ----------

def pick_random_question(db: Session, couple_id: str, pack_id: Optional[int] = None) -> Optional[models.Question]:
    """Если pack_id задан, вопрос выбирается только из этого пака (он должен
    быть в числе открытых для пары); иначе — из любого открытого пака."""
    played_ids = [
        row[0]
        for row in db.query(models.CoupleQuestionHistory.question_id)
        .filter(models.CoupleQuestionHistory.couple_id == couple_id)
        .all()
    ]
    unlocked_pack_ids = get_unlocked_pack_ids(db, couple_id)

    if pack_id is not None:
        if pack_id not in unlocked_pack_ids:
            return None
        pack_filter_ids = [pack_id]
    else:
        pack_filter_ids = unlocked_pack_ids

    query = db.query(models.Question).filter(
        models.Question.is_active.is_(True),
        models.Question.pack_id.in_(pack_filter_ids) if pack_filter_ids else sa_false(),
    )
    if played_ids:
        query = query.filter(~models.Question.id.in_(played_ids))

    candidates = query.all()
    if not candidates:
        return None
    return random.choice(candidates)


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
