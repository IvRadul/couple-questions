import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Пользователь. Создаётся автоматически (анонимно) при первом обращении.
    Опционально может "закрепить" аккаунт логином/паролем (username +
    password_hash) — тогда с него можно будет войти на другом устройстве
    без потери прогресса. Пока username не задан, аккаунт остаётся чисто
    анонимным и доступен только через токен, сохранённый в localStorage.
    Весь прогресс (монеты, достижения, статистика) хранится на пользователе,
    а не на паре — поэтому смена/расформирование пары не обнуляет прогресс."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    display_name = Column(String, nullable=True)
    username = Column(String(32), unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=True)
    coins = Column(Integer, default=0, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    couple_id = Column(String, ForeignKey("couples.id"), nullable=True)
    couple = relationship("Couple", back_populates="members", foreign_keys=[couple_id])

    answers = relationship("Answer", back_populates="user")
    ratings = relationship("Rating", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    pack_unlocks = relationship("CouplePackUnlock", back_populates="unlocked_by")

    # Простая счётная статистика, нужна для проверки условий достижений
    total_games = Column(Integer, default=0, nullable=False)
    current_match_streak = Column(Integer, default=0, nullable=False)
    best_match_streak = Column(Integer, default=0, nullable=False)
    questions_rated_count = Column(Integer, default=0, nullable=False)
    fastest_answer_seconds = Column(Integer, nullable=True)


class CoupleStatus(str, enum.Enum):
    pending = "pending"      # код создан, ждём второго партнёра
    active = "active"        # оба партнёра подключены
    disbanded = "disbanded"  # пара расформирована (кто-то из партнёров ушёл)


class Couple(Base):
    """Пара из двух пользователей, связанных по коду приглашения.
    Пользователь может со временем состоять в нескольких парах по очереди —
    старые пары остаются в базе как есть (со своей историей вопросов и
    раундов), просто пользователь на них больше не ссылается."""

    __tablename__ = "couples"

    id = Column(String, primary_key=True, default=gen_uuid)
    invite_code = Column(String(6), unique=True, index=True, nullable=False)
    status = Column(Enum(CoupleStatus), default=CoupleStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("User", back_populates="couple", foreign_keys=[User.couple_id])
    history = relationship("CoupleQuestionHistory", back_populates="couple")
    rounds = relationship("GameRound", back_populates="couple")
    pack_unlocks = relationship("CouplePackUnlock", back_populates="couple")


class QuestionType(str, enum.Enum):
    open = "open"      # Тип 1: свободный текстовый ответ, совпадение подтверждает отвечавший вручную
    choice = "choice"  # Тип 2: выбор из готовых вариантов, совпадение считается автоматически


class PackStatus(str, enum.Enum):
    pending = "pending"    # предложен пользователем, ждёт модерации
    approved = "approved"  # прошёл проверку (или создан админом) — доступен для игры
    rejected = "rejected"  # отклонён администратором


class QuestionPack(Base):
    """Набор (пак) вопросов на одну тему. Стартовый пак бесплатный,
    остальные открываются за монеты (за пару, не за отдельного пользователя).
    Паки может создавать администратор (сразу approved) или обычный
    пользователь (уходит на модерацию со статусом pending)."""

    __tablename__ = "question_packs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(String(256), nullable=True)
    price_coins = Column(Integer, default=0, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    status = Column(Enum(PackStatus), default=PackStatus.approved, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # для мягкого скрытия админом
    created_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(String(256), nullable=True)

    questions = relationship("Question", back_populates="pack")
    unlocks = relationship("CouplePackUnlock", back_populates="pack")


class Question(Base):
    """Вопрос об отношениях из общей базы вопросов."""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    category = Column(String(64), default="general", nullable=False)
    question_type = Column(Enum(QuestionType), default=QuestionType.open, nullable=False)
    pack_id = Column(Integer, ForeignKey("question_packs.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Денормализованные агрегаты рейтинга — для быстрых топ-выборок
    rating_sum = Column(Integer, default=0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    report_count = Column(Integer, default=0, nullable=False)

    pack = relationship("QuestionPack", back_populates="questions")
    ratings = relationship("Rating", back_populates="question")
    options = relationship(
        "QuestionOption", back_populates="question", order_by="QuestionOption.sort_order"
    )

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.rating_sum / self.rating_count, 2)


class QuestionOption(Base):
    """Вариант ответа для вопроса типа 'choice' (Тип 2)."""

    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    text = Column(String(256), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    question = relationship("Question", back_populates="options")


class CouplePackUnlock(Base):
    """Какие паки вопросов пара уже открыла за монеты."""

    __tablename__ = "couple_pack_unlocks"
    __table_args__ = (UniqueConstraint("couple_id", "pack_id", name="uq_couple_pack"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    couple_id = Column(String, ForeignKey("couples.id"), nullable=False)
    pack_id = Column(Integer, ForeignKey("question_packs.id"), nullable=False)
    unlocked_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    unlocked_at = Column(DateTime, default=datetime.utcnow)

    couple = relationship("Couple", back_populates="pack_unlocks")
    pack = relationship("QuestionPack", back_populates="unlocks")
    unlocked_by = relationship("User", back_populates="pack_unlocks")


class CoupleQuestionHistory(Base):
    """Какие вопросы пара уже проходила — чтобы не повторяться."""

    __tablename__ = "couple_question_history"
    __table_args__ = (UniqueConstraint("couple_id", "question_id", name="uq_couple_question"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    couple_id = Column(String, ForeignKey("couples.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    played_at = Column(DateTime, default=datetime.utcnow)

    couple = relationship("Couple", back_populates="history")
    question = relationship("Question")


class RoundStatus(str, enum.Enum):
    waiting_answer = "waiting_answer"          # ждём ответа того, кто отвечает "за себя"
    waiting_guess = "waiting_guess"            # отвечавший ответил, ждём догадку второго партнёра
    waiting_validation = "waiting_validation"  # только для типа 'open': ждём ручную проверку отвечавшего
    completed = "completed"


class GameRound(Base):
    """Один раунд игры. Роли на раунд назначаются случайно:
    answerer — отвечает на вопрос "про себя" первым;
    guesser — пытается угадать, что ответил партнёр, не видя его ответа."""

    __tablename__ = "game_rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    couple_id = Column(String, ForeignKey("couples.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    answerer_id = Column(String, ForeignKey("users.id"), nullable=False)
    guesser_id = Column(String, ForeignKey("users.id"), nullable=False)

    status = Column(Enum(RoundStatus), default=RoundStatus.waiting_answer, nullable=False)
    is_match = Column(Boolean, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    couple = relationship("Couple", back_populates="rounds")
    question = relationship("Question")
    answers = relationship("Answer", back_populates="round")
    answerer = relationship("User", foreign_keys=[answerer_id])
    guesser = relationship("User", foreign_keys=[guesser_id])


class Answer(Base):
    """Ответ одного пользователя в рамках конкретного раунда.
    Для вопросов типа 'choice' используется selected_option_id,
    для 'open' — свободный текст в поле text."""

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("round_id", "user_id", name="uq_round_user"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(Integer, ForeignKey("game_rounds.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    selected_option_id = Column(Integer, ForeignKey("question_options.id"), nullable=True)
    answered_at = Column(DateTime, default=datetime.utcnow)
    response_time_seconds = Column(Integer, nullable=True)

    round = relationship("GameRound", back_populates="answers")
    user = relationship("User", back_populates="answers")
    selected_option = relationship("QuestionOption")


class Rating(Base):
    """Оценка вопроса пользователем (1-5) либо жалоба."""

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("question_id", "user_id", "round_id", name="uq_rating_once"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    round_id = Column(Integer, ForeignKey("game_rounds.id"), nullable=True)
    stars = Column(Integer, nullable=True)  # 1-5, null если это просто жалоба
    is_report = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    question = relationship("Question", back_populates="ratings")
    user = relationship("User", back_populates="ratings")


class Achievement(Base):
    """Справочник достижений."""

    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)
    title = Column(String(128), nullable=False)
    description = Column(String(256), nullable=False)
    coin_reward = Column(Integer, default=0, nullable=False)


class UserAchievement(Base):
    """Полученные пользователем достижения."""

    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    earned_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement")
