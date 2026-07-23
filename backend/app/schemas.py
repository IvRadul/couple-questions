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


# ---------- Question ----------

class QuestionOut(BaseModel):
    id: int
    text: str
    category: str
    average_rating: float
    rating_count: int

    class Config:
        from_attributes = True


class QuestionAdminOut(QuestionOut):
    is_active: bool
    report_count: int


class QuestionCreate(BaseModel):
    text: str
    category: str = "general"


# ---------- Game round ----------

class StartRoundResponse(BaseModel):
    round_id: int
    question: QuestionOut
    first_responder_id: str
    second_responder_id: str
    your_turn: bool  # можете ли вы отвечать прямо сейчас


class SubmitAnswerRequest(BaseModel):
    round_id: int
    text: str


class AnswerOut(BaseModel):
    user_id: str
    text: str

    class Config:
        from_attributes = True


class RoundResultOut(BaseModel):
    round_id: int
    question: QuestionOut
    answers: List[AnswerOut]
    is_match: bool
    points_awarded: int
    coins_awarded: int


class RateQuestionRequest(BaseModel):
    question_id: int
    round_id: Optional[int] = None
    stars: Optional[int] = Field(default=None, ge=1, le=5)
    is_report: bool = False


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
    answers: List[AnswerOut]
    is_match: bool
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
