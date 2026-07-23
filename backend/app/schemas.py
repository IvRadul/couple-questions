from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ---------- Auth ----------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    couple_id: Optional[str] = None


class UserOut(BaseModel):
    id: str
    display_name: Optional[str]
    coins: int
    is_admin: bool
    couple_id: Optional[str]
    total_games: int
    best_match_streak: int

    class Config:
        from_attributes = True


# ---------- Couple ----------

class CoupleCreateResponse(BaseModel):
    couple_id: str
    invite_code: str
    status: str
    access_token: str


class CoupleJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=6, max_length=6)


class CoupleOut(BaseModel):
    id: str
    invite_code: str
    status: str
    members: List[UserOut]

    class Config:
        from_attributes = True


# ---------- Question packs ----------

class PackOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price_coins: int
    is_default: bool
    question_count: int
    unlocked: bool

    class Config:
        from_attributes = True


class PackUnlockResponse(BaseModel):
    pack_id: int
    remaining_coins: int


# ---------- Question ----------

class QuestionOptionOut(BaseModel):
    id: int
    text: str

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    text: str
    category: str
    question_type: str
    options: List[QuestionOptionOut] = []
    average_rating: float
    rating_count: int

    class Config:
        from_attributes = True


class QuestionAdminOut(QuestionOut):
    is_active: bool
    report_count: int
    pack_id: Optional[int]


class QuestionOptionCreate(BaseModel):
    text: str


class QuestionCreate(BaseModel):
    text: str
    category: str = "general"
    question_type: str = "open"
    pack_id: Optional[int] = None
    options: List[QuestionOptionCreate] = []


# ---------- Game round ----------

class RateQuestionRequest(BaseModel):
    question_id: int
    round_id: Optional[int] = None
    stars: Optional[int] = Field(default=None, ge=1, le=5)
    is_report: bool = False


class AnswerOut(BaseModel):
    user_id: str
    text: str
    selected_option_id: Optional[int] = None

    class Config:
        from_attributes = True


# ---------- Achievements ----------

class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    coin_reward: int
    earned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- History ----------

class HistoryItemOut(BaseModel):
    round_id: int
    question_text: str
    question_type: str
    answerer_id: str
    guesser_id: str
    answers: List[AnswerOut]
    is_match: bool
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
