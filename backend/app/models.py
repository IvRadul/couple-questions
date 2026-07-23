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
    """Анонимный пользователь. Создаётся автоматически при первом обращении."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    display_name = Column(String, nullable=True)
    coins = Column(Integer, default=0, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    couple_id = Column(String, ForeignKey("couples.id"), nullable=True)
    couple = relationship("Couple", back_populates="members", foreign_keys=[couple_id])

    answers = relationship("Answer", back_populates="user")
    ratings = relationship("Rating", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")

    # Простая счётная статистика, нужна для проверки условий достижений
    total_games = Column(Integer, default=0, nullable=False)
    current_match_streak = Column(Integer, default=0, nullable=False)
    best_match_streak = Column(Integer, default=0, nullable=False)
    questions_rated_count = Column(Integer, default=0, nullable=False)
    fastest_answer_seconds = Column(Integer, nullable=True)


class CoupleStatus(str, enum.Enum):
    pending = "pending"  # код создан, ждём второго партнёра
    active = "active"    # оба партнёра подключены


class Couple(Base):
    """Пара из двух пользователей, связанных по коду приглашения."""

    __tablename__ = "couples"

    id = Column(String, primary_key=True, default=gen_uuid)
    invite_code = Column(String(6), unique=True, index=True, nullable=False)
    status = Column(Enum(CoupleStatus), default=CoupleStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("User", back_populates="couple", foreign_keys=[User.couple_id])
    history = relationship("CoupleQuestionHistory", back_populates="couple")
    rounds = relationship("GameRound", back_populates="couple")


class Question(Base):
    """Вопрос об отношениях из общей базы вопросов."""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    category = Column(String(64), default="general", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Денормализованные агрегаты рейтинга — для быстрых топ-выборок
    rating_sum = Column(Integer, default=0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    report_count = Column(Integer, default=0, nullable=False)

    ratings = relationship("Rating", back_populates="question")

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.rating_sum / self.rating_count, 2)


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
    waiting_first = "waiting_first"    # ждём ответа того, кто отвечает первым
    waiting_second = "waiting_second"  # первый ответил, ждём второго
    completed = "completed"


class GameRound(Base):
    """Один раунд игры: вопрос, кто отвечает первым, статус, результат."""

    __tablename__ = "game_rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    couple_id = Column(String, ForeignKey("couples.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    first_responder_id = Column(String, ForeignKey("users.id"), nullable=False)
    second_responder_id = Column(String, ForeignKey("users.id"), nullable=False)

    status = Column(Enum(RoundStatus), default=RoundStatus.waiting_first, nullable=False)
    is_match = Column(Boolean, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    couple = relationship("Couple", back_populates="rounds")
    question = relationship("Question")
    answers = relationship("Answer", back_populates="round")


class Answer(Base):
    """Ответ одного пользователя в рамках конкретного раунда."""

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("round_id", "user_id", name="uq_round_user"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(Integer, ForeignKey("game_rounds.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    response_time_seconds = Column(Integer, nullable=True)

    round = relationship("GameRound", back_populates="answers")
    user = relationship("User", back_populates="answers")


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
