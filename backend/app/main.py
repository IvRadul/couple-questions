from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.routers import auth, couples, questions, game
from app.seed_data import run_all_seeds
from app.auth import get_current_user
from app.schemas import UserOut

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Вопросы для пары API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(couples.router)
app.include_router(questions.router)
app.include_router(game.router)


@app.on_event("startup")
def on_startup():
    db: Session = next(get_db())
    run_all_seeds(db)
    db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/users/me", response_model=UserOut)
def get_me(user=Depends(get_current_user)):
    return user
