import random
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.auth import get_current_user, decode_token_for_ws
from app import models, crud
from app.schemas import HistoryItemOut, AnswerOut, AchievementOut
from app.websocket_manager import manager

router = APIRouter(tags=["game"])

MATCH_POINTS = 10
MATCH_COINS = 5
NO_MATCH_COINS = 2


# --------------------------------------------------------------------------
# REST: история игр пары
# --------------------------------------------------------------------------

@router.get("/game/history", response_model=List[HistoryItemOut])
def get_history(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.couple_id:
        raise HTTPException(status_code=400, detail="Вы не состоите в паре")

    rounds = (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == user.couple_id,
            models.GameRound.status == models.RoundStatus.completed,
        )
        .order_by(models.GameRound.completed_at.desc())
        .all()
    )

    result = []
    for r in rounds:
        answers = [AnswerOut(user_id=a.user_id, text=a.text) for a in r.answers]
        result.append(
            HistoryItemOut(
                round_id=r.id,
                question_text=r.question.text,
                answers=answers,
                is_match=bool(r.is_match),
                completed_at=r.completed_at,
            )
        )
    return result


@router.get("/achievements/me", response_model=List[AchievementOut])
def my_achievements(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.UserAchievement)
        .filter(models.UserAchievement.user_id == user.id)
        .all()
    )
    return [
        AchievementOut(
            code=row.achievement.code,
            title=row.achievement.title,
            description=row.achievement.description,
            coin_reward=row.achievement.coin_reward,
            earned_at=row.earned_at,
        )
        for row in rows
    ]


# --------------------------------------------------------------------------
# WebSocket: синхронизация раунда в реальном времени
#
# Протокол (JSON-сообщения):
#   Клиент -> Сервер:
#     {"action": "start_round"}
#     {"action": "submit_answer", "round_id": 1, "text": "..."}
#
#   Сервер -> Клиент(ы):
#     {"action": "round_started", "round_id", "question", "first_responder_id", "second_responder_id"}
#     {"action": "answer_saved"}                      -> только тому, кто только что ответил первым
#     {"action": "your_turn", "round_id"}              -> второму партнёру, когда можно отвечать
#     {"action": "round_result", "round_id", "question", "answers", "is_match", "points_awarded", "coins_awarded"}
#     {"action": "new_achievement", "achievement": {...}}
#     {"action": "error", "detail": "..."}
# --------------------------------------------------------------------------

def _build_round_sync_messages(game_round: models.GameRound, target_user_id: str) -> list:
    """Собирает сообщения, которые нужно отправить клиенту, чтобы он
    догнал текущее состояние уже идущего раунда (например, если клиент
    подключился/переподключился после того, как раунд был запущен, и
    пропустил исходную рассылку 'round_started')."""
    question = game_round.question
    messages: list = [
        {
            "action": "round_started",
            "round_id": game_round.id,
            "question": {"id": question.id, "text": question.text, "category": question.category},
            "first_responder_id": game_round.first_responder_id,
            "second_responder_id": game_round.second_responder_id,
        }
    ]

    if game_round.status == models.RoundStatus.waiting_second:
        if target_user_id == game_round.second_responder_id:
            # Первый уже ответил, сейчас очередь этого пользователя
            messages.append({"action": "your_turn", "round_id": game_round.id})
        elif target_user_id == game_round.first_responder_id:
            # Этот пользователь уже отвечал — переводим его в состояние ожидания
            messages.append({"action": "answer_saved", "round_id": game_round.id})

    return messages


async def _sync_user_with_active_round(db: Session, couple_id: str, user_id: str) -> None:
    active_round = (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == couple_id,
            models.GameRound.status != models.RoundStatus.completed,
        )
        .first()
    )
    if active_round is None:
        return
    for msg in _build_round_sync_messages(active_round, user_id):
        await manager.send_to_user(couple_id, user_id, msg)


@router.websocket("/ws/{couple_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    couple_id: str,
    token: str = Query(...),
):
    db = SessionLocal()
    try:
        user = decode_token_for_ws(token, db)
        if user is None or user.couple_id != couple_id:
            await websocket.close(code=4401)
            return

        couple = db.query(models.Couple).filter(models.Couple.id == couple_id).first()
        if couple is None or couple.status != models.CoupleStatus.active:
            await websocket.close(code=4404)
            return

        await manager.connect(couple_id, user.id, websocket)

        # Если в паре уже идёт раунд (например, партнёр начал его раньше, чем
        # этот клиент успел подключиться), сразу подгружаем его состояние —
        # иначе пользователь так и останется на экране "Начать раунд".
        await _sync_user_with_active_round(db, couple_id, user.id)

        try:
            while True:
                message = await websocket.receive_json()
                action = message.get("action")

                if action == "start_round":
                    await _handle_start_round(db, couple, user)
                elif action == "submit_answer":
                    await _handle_submit_answer(db, couple, user, message)
                else:
                    await manager.send_to_user(
                        couple_id, user.id, {"action": "error", "detail": f"Неизвестное действие: {action}"}
                    )
        except WebSocketDisconnect:
            manager.disconnect(couple_id, user.id)
    finally:
        db.close()


async def _handle_start_round(db: Session, couple: models.Couple, requester: models.User) -> None:
    # Не даём начать новый раунд, пока есть незавершённый
    active_round = (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == couple.id,
            models.GameRound.status != models.RoundStatus.completed,
        )
        .first()
    )
    if active_round is not None:
        # Раунд уже идёт (скорее всего партнёр начал его первым, а этот клиент
        # пропустил рассылку) — вместо тупиковой ошибки досылаем ему текущее
        # состояние раунда, чтобы интерфейс синхронизировался.
        for msg in _build_round_sync_messages(active_round, requester.id):
            await manager.send_to_user(couple.id, requester.id, msg)
        return

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if len(members) != 2:
        await manager.send_to_user(
            couple.id, requester.id, {"action": "error", "detail": "В паре должно быть двое участников"}
        )
        return

    question = crud.pick_random_question(db, couple.id)
    if question is None:
        await manager.send_to_user(
            couple.id,
            requester.id,
            {"action": "error", "detail": "Вопросы закончились — пара прошла всю базу!"},
        )
        return

    first, second = random.sample(members, 2)

    game_round = models.GameRound(
        couple_id=couple.id,
        question_id=question.id,
        first_responder_id=first.id,
        second_responder_id=second.id,
        status=models.RoundStatus.waiting_first,
    )
    db.add(game_round)
    db.commit()
    db.refresh(game_round)

    payload = {
        "action": "round_started",
        "round_id": game_round.id,
        "question": {"id": question.id, "text": question.text, "category": question.category},
        "first_responder_id": first.id,
        "second_responder_id": second.id,
    }
    await manager.broadcast_to_couple(couple.id, payload)


async def _handle_submit_answer(
    db: Session, couple: models.Couple, user: models.User, message: dict
) -> None:
    round_id = message.get("round_id")
    text = (message.get("text") or "").strip()

    if not text:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Ответ не может быть пустым"})
        return

    game_round = (
        db.query(models.GameRound)
        .filter(models.GameRound.id == round_id, models.GameRound.couple_id == couple.id)
        .first()
    )
    if game_round is None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд не найден"})
        return

    now = datetime.utcnow()

    if game_round.status == models.RoundStatus.waiting_first:
        if user.id != game_round.first_responder_id:
            await manager.send_to_user(
                couple.id, user.id, {"action": "error", "detail": "Сейчас не ваша очередь отвечать"}
            )
            return

        response_time = int((now - game_round.created_at).total_seconds())
        answer = models.Answer(
            round_id=game_round.id, user_id=user.id, text=text, response_time_seconds=response_time
        )
        db.add(answer)
        game_round.status = models.RoundStatus.waiting_second
        db.commit()

        await manager.send_to_user(couple.id, user.id, {"action": "answer_saved", "round_id": game_round.id})
        await manager.send_to_user(
            couple.id, game_round.second_responder_id, {"action": "your_turn", "round_id": game_round.id}
        )
        return

    if game_round.status == models.RoundStatus.waiting_second:
        if user.id != game_round.second_responder_id:
            await manager.send_to_user(
                couple.id, user.id, {"action": "error", "detail": "Сейчас не ваша очередь отвечать"}
            )
            return

        first_answer = (
            db.query(models.Answer)
            .filter(models.Answer.round_id == game_round.id, models.Answer.user_id == game_round.first_responder_id)
            .first()
        )
        response_time = int((now - first_answer.answered_at).total_seconds())
        second_answer = models.Answer(
            round_id=game_round.id, user_id=user.id, text=text, response_time_seconds=response_time
        )
        db.add(second_answer)

        is_match = crud.answers_match(first_answer.text, text)
        game_round.status = models.RoundStatus.completed
        game_round.is_match = is_match
        game_round.completed_at = now
        db.add(
            models.CoupleQuestionHistory(couple_id=couple.id, question_id=game_round.question_id)
        )

        first_user = db.query(models.User).filter(models.User.id == game_round.first_responder_id).first()
        second_user = user

        points_awarded = MATCH_POINTS if is_match else 0
        coins_awarded = MATCH_COINS if is_match else NO_MATCH_COINS

        for u, resp_time in (
            (first_user, first_answer.response_time_seconds),
            (second_user, second_answer.response_time_seconds),
        ):
            u.coins += coins_awarded
            u.total_games += 1
            if is_match:
                u.current_match_streak += 1
                u.best_match_streak = max(u.best_match_streak, u.current_match_streak)
            else:
                u.current_match_streak = 0
            if resp_time is not None and (u.fastest_answer_seconds is None or resp_time < u.fastest_answer_seconds):
                u.fastest_answer_seconds = resp_time

        db.commit()

        question = game_round.question
        result_payload = {
            "action": "round_result",
            "round_id": game_round.id,
            "question": {"id": question.id, "text": question.text, "category": question.category},
            "answers": [
                {"user_id": first_user.id, "text": first_answer.text},
                {"user_id": second_user.id, "text": second_answer.text},
            ],
            "is_match": is_match,
            "points_awarded": points_awarded,
            "coins_awarded": coins_awarded,
        }
        await manager.broadcast_to_couple(couple.id, result_payload)

        # Проверка достижений для обоих участников
        for u, resp_time in (
            (first_user, first_answer.response_time_seconds),
            (second_user, second_answer.response_time_seconds),
        ):
            new_achievements = crud.check_achievements_after_round(db, u, resp_time)
            for ach in new_achievements:
                await manager.send_to_user(
                    couple.id,
                    u.id,
                    {
                        "action": "new_achievement",
                        "achievement": {
                            "code": ach.code,
                            "title": ach.title,
                            "description": ach.description,
                            "coin_reward": ach.coin_reward,
                        },
                    },
                )
        return

    await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд уже завершён"})
