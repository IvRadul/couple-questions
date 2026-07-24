import random
from datetime import datetime
from typing import List, Optional

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
        answers = [
            AnswerOut(user_id=a.user_id, text=a.text, selected_option_id=a.selected_option_id)
            for a in r.answers
        ]
        result.append(
            HistoryItemOut(
                round_id=r.id,
                question_text=r.question.text,
                question_type=r.question.question_type.value,
                answerer_id=r.answerer_id,
                guesser_id=r.guesser_id,
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
# Перед раундом один из партнёров выбирает пак вопросов и предлагает сыграть
# именно в него — второй партнёр должен принять или отклонить предложение,
# только после этого создаётся сам раунд. Роли внутри раунда назначаются
# случайно:
#   answerer — отвечает на вопрос "про себя" первым.
#   guesser  — пытается угадать ответ партнёра, не видя его.
#
# Разрешение раунда зависит от типа вопроса:
#   question_type == "choice" -> сравнение вариантов автоматическое.
#   question_type == "open"   -> после догадки guesser'а решение о совпадении
#                                  принимает вручную answerer (кнопка validate_answer).
#
# Протокол (JSON-сообщения):
#   Клиент -> Сервер:
#     {"action": "propose_round", "pack_id": 1}
#     {"action": "respond_round_proposal", "pack_id": 1, "accept": true}
#     {"action": "submit_answer", "round_id": 1, "text": "...", "option_id": null}
#     {"action": "validate_answer", "round_id": 1, "is_match": true}
#
#   Сервер -> Клиент(ы):
#     {"action": "round_proposed", "pack_id", "pack_name", "proposer_id"}  -> партнёру, которому предложили
#     {"action": "round_declined", "pack_id"}                              -> инициатору, если партнёр отказался
#     {"action": "round_started", "round_id", "question": {..., "question_type", "options"},
#      "answerer_id", "guesser_id"}
#     {"action": "answer_saved", "round_id"}                 -> отвечавшему, когда его ответ сохранён
#     {"action": "your_turn", "round_id"}                    -> угадывающему, когда можно отвечать
#     {"action": "awaiting_validation", "round_id"}           -> угадывающему, пока идёт ручная проверка
#     {"action": "validate_request", "round_id", "your_answer", "guess"}  -> отвечавшему, для проверки
#     {"action": "round_result", "round_id", "question", "answers", "is_match",
#      "points_awarded", "coins_awarded"}
#     {"action": "new_achievement", "achievement": {...}}
#     {"action": "error", "detail": "..."}
#
# Предложение раунда не хранится в БД (это лёгкий, недолговечный обмен) —
# если партнёр в момент предложения не подключён к WebSocket, сообщение
# теряется, как и с обычными уведомлениями хода; повторное предложение
# решает эту ситуацию.
# --------------------------------------------------------------------------

def _question_payload(question: models.Question) -> dict:
    return {
        "id": question.id,
        "text": question.text,
        "category": question.category,
        "question_type": question.question_type.value,
        "options": [{"id": o.id, "text": o.text} for o in question.options],
    }


def _build_round_sync_messages(game_round: models.GameRound, target_user_id: str) -> list:
    """Собирает сообщения, которые нужно отправить клиенту, чтобы он
    догнал текущее состояние уже идущего раунда (например, если клиент
    подключился/переподключился после того, как раунд был запущен, и
    пропустил исходную рассылку 'round_started')."""
    messages: list = [
        {
            "action": "round_started",
            "round_id": game_round.id,
            "question": _question_payload(game_round.question),
            "answerer_id": game_round.answerer_id,
            "guesser_id": game_round.guesser_id,
        }
    ]

    if game_round.status == models.RoundStatus.waiting_guess:
        if target_user_id == game_round.guesser_id:
            messages.append({"action": "your_turn", "round_id": game_round.id})
        elif target_user_id == game_round.answerer_id:
            messages.append({"action": "answer_saved", "round_id": game_round.id})

    elif game_round.status == models.RoundStatus.waiting_validation:
        answerer_answer = next((a for a in game_round.answers if a.user_id == game_round.answerer_id), None)
        guesser_answer = next((a for a in game_round.answers if a.user_id == game_round.guesser_id), None)
        if target_user_id == game_round.answerer_id and answerer_answer and guesser_answer:
            messages.append(
                {
                    "action": "validate_request",
                    "round_id": game_round.id,
                    "your_answer": answerer_answer.text,
                    "guess": guesser_answer.text,
                }
            )
        elif target_user_id == game_round.guesser_id:
            messages.append({"action": "awaiting_validation", "round_id": game_round.id})

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

                if action == "propose_round":
                    await _handle_propose_round(db, couple, user, message)
                elif action == "respond_round_proposal":
                    await _handle_respond_round_proposal(db, couple, user, message)
                elif action == "submit_answer":
                    await _handle_submit_answer(db, couple, user, message)
                elif action == "validate_answer":
                    await _handle_validate_answer(db, couple, user, message)
                else:
                    await manager.send_to_user(
                        couple_id, user.id, {"action": "error", "detail": f"Неизвестное действие: {action}"}
                    )
        except WebSocketDisconnect:
            manager.disconnect(couple_id, user.id)
    finally:
        db.close()


async def _handle_propose_round(db: Session, couple: models.Couple, proposer: models.User, message: dict) -> None:
    # Не даём предложить новый раунд, пока есть незавершённый
    active_round = (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == couple.id,
            models.GameRound.status != models.RoundStatus.completed,
        )
        .first()
    )
    if active_round is not None:
        # Раунд уже идёт (скорее всего партнёр начал его раньше, а этот клиент
        # пропустил рассылку) — вместо тупиковой ошибки досылаем ему текущее
        # состояние раунда, чтобы интерфейс синхронизировался.
        for msg in _build_round_sync_messages(active_round, proposer.id):
            await manager.send_to_user(couple.id, proposer.id, msg)
        return

    pack_id = message.get("pack_id")
    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        await manager.send_to_user(couple.id, proposer.id, {"action": "error", "detail": "Пак не найден"})
        return

    unlocked_ids = crud.get_unlocked_pack_ids(db, couple.id)
    if pack.id not in unlocked_ids:
        await manager.send_to_user(
            couple.id, proposer.id, {"action": "error", "detail": "Этот пак ещё не открыт для вашей пары"}
        )
        return

    if crud.pick_random_question(db, couple.id, pack_id=pack.id) is None:
        await manager.send_to_user(
            couple.id,
            proposer.id,
            {"action": "error", "detail": "В этом паке не осталось новых вопросов для вашей пары"},
        )
        return

    # Предложение — лёгкий, недолговечный обмен (не хранится в БД): если партнёр
    # в этот момент не подключён к WebSocket, сообщение теряется так же, как и
    # обычные уведомления о ходе — достаточно предложить ещё раз.
    await manager.broadcast_to_couple(
        couple.id,
        {
            "action": "round_proposed",
            "pack_id": pack.id,
            "pack_name": pack.name,
            "proposer_id": proposer.id,
        },
    )


async def _handle_respond_round_proposal(
    db: Session, couple: models.Couple, responder: models.User, message: dict
) -> None:
    pack_id = message.get("pack_id")
    accept = bool(message.get("accept"))

    if not accept:
        await manager.broadcast_to_couple(couple.id, {"action": "round_declined", "pack_id": pack_id})
        return

    # Не даём создать дубликат раунда, если он уже успел появиться
    # (например, из-за повторного клика "Принять" в двух вкладках).
    active_round = (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == couple.id,
            models.GameRound.status != models.RoundStatus.completed,
        )
        .first()
    )
    if active_round is not None:
        for msg in _build_round_sync_messages(active_round, responder.id):
            await manager.send_to_user(couple.id, responder.id, msg)
        return

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if len(members) != 2:
        await manager.send_to_user(
            couple.id, responder.id, {"action": "error", "detail": "В паре должно быть двое участников"}
        )
        return

    question = crud.pick_random_question(db, couple.id, pack_id=pack_id)
    if question is None:
        await manager.broadcast_to_couple(
            couple.id,
            {"action": "error", "detail": "Вопросы в этом паке закончились, выберите другой пак"},
        )
        return

    answerer, guesser = random.sample(members, 2)

    game_round = models.GameRound(
        couple_id=couple.id,
        question_id=question.id,
        answerer_id=answerer.id,
        guesser_id=guesser.id,
        status=models.RoundStatus.waiting_answer,
    )
    db.add(game_round)
    db.commit()
    db.refresh(game_round)

    payload = {
        "action": "round_started",
        "round_id": game_round.id,
        "question": _question_payload(question),
        "answerer_id": answerer.id,
        "guesser_id": guesser.id,
    }
    await manager.broadcast_to_couple(couple.id, payload)


def _validate_submitted_answer(question: models.Question, text: str, option_id) -> Optional[models.QuestionOption]:
    """Для вопросов типа 'choice' проверяет, что option_id указывает на
    вариант этого вопроса, и возвращает выбранный вариант."""
    if question.question_type != models.QuestionType.choice:
        return None
    option = next((o for o in question.options if o.id == option_id), None)
    if option is None:
        raise ValueError("Нужно выбрать один из предложенных вариантов")
    return option


async def _handle_submit_answer(
    db: Session, couple: models.Couple, user: models.User, message: dict
) -> None:
    round_id = message.get("round_id")
    text = (message.get("text") or "").strip()
    option_id = message.get("option_id")

    game_round = (
        db.query(models.GameRound)
        .filter(models.GameRound.id == round_id, models.GameRound.couple_id == couple.id)
        .first()
    )
    if game_round is None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд не найден"})
        return

    question = game_round.question

    selected_option = None
    if question.question_type == models.QuestionType.choice:
        try:
            selected_option = _validate_submitted_answer(question, text, option_id)
        except ValueError as e:
            await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": str(e)})
            return
        text = selected_option.text
    elif not text:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Ответ не может быть пустым"})
        return

    now = datetime.utcnow()

    if game_round.status == models.RoundStatus.waiting_answer:
        if user.id != game_round.answerer_id:
            await manager.send_to_user(
                couple.id, user.id, {"action": "error", "detail": "Сейчас не ваша очередь отвечать"}
            )
            return

        response_time = int((now - game_round.created_at).total_seconds())
        answer = models.Answer(
            round_id=game_round.id,
            user_id=user.id,
            text=text,
            selected_option_id=selected_option.id if selected_option else None,
            response_time_seconds=response_time,
        )
        db.add(answer)
        game_round.status = models.RoundStatus.waiting_guess
        db.commit()

        await manager.send_to_user(couple.id, user.id, {"action": "answer_saved", "round_id": game_round.id})
        await manager.send_to_user(
            couple.id, game_round.guesser_id, {"action": "your_turn", "round_id": game_round.id}
        )
        return

    if game_round.status == models.RoundStatus.waiting_guess:
        if user.id != game_round.guesser_id:
            await manager.send_to_user(
                couple.id, user.id, {"action": "error", "detail": "Сейчас не ваша очередь отвечать"}
            )
            return

        answerer_answer = (
            db.query(models.Answer)
            .filter(models.Answer.round_id == game_round.id, models.Answer.user_id == game_round.answerer_id)
            .first()
        )
        response_time = int((now - answerer_answer.answered_at).total_seconds())
        guess_answer = models.Answer(
            round_id=game_round.id,
            user_id=user.id,
            text=text,
            selected_option_id=selected_option.id if selected_option else None,
            response_time_seconds=response_time,
        )
        db.add(guess_answer)

        if question.question_type == models.QuestionType.choice:
            # Варианты фиксированы — можно сравнивать автоматически.
            is_match = (
                answerer_answer.selected_option_id is not None
                and answerer_answer.selected_option_id == guess_answer.selected_option_id
            )
            db.commit()
            await _finalize_round(db, couple, game_round, answerer_answer, guess_answer, is_match)
        else:
            # Свободный текст — финальное решение о совпадении принимает answerer вручную.
            game_round.status = models.RoundStatus.waiting_validation
            db.commit()
            await manager.send_to_user(
                couple.id,
                game_round.answerer_id,
                {
                    "action": "validate_request",
                    "round_id": game_round.id,
                    "your_answer": answerer_answer.text,
                    "guess": guess_answer.text,
                },
            )
            await manager.send_to_user(
                couple.id, game_round.guesser_id, {"action": "awaiting_validation", "round_id": game_round.id}
            )
        return

    await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд уже завершён"})


async def _handle_validate_answer(
    db: Session, couple: models.Couple, user: models.User, message: dict
) -> None:
    round_id = message.get("round_id")
    is_match = bool(message.get("is_match"))

    game_round = (
        db.query(models.GameRound)
        .filter(models.GameRound.id == round_id, models.GameRound.couple_id == couple.id)
        .first()
    )
    if game_round is None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд не найден"})
        return

    if game_round.status != models.RoundStatus.waiting_validation:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Раунд не ожидает проверки"})
        return

    if user.id != game_round.answerer_id:
        await manager.send_to_user(
            couple.id, user.id, {"action": "error", "detail": "Подтвердить совпадение может только отвечавший"}
        )
        return

    answerer_answer = next((a for a in game_round.answers if a.user_id == game_round.answerer_id), None)
    guess_answer = next((a for a in game_round.answers if a.user_id == game_round.guesser_id), None)
    if answerer_answer is None or guess_answer is None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Не найдены ответы раунда"})
        return

    await _finalize_round(db, couple, game_round, answerer_answer, guess_answer, is_match)


async def _finalize_round(
    db: Session,
    couple: models.Couple,
    game_round: models.GameRound,
    answerer_answer: models.Answer,
    guess_answer: models.Answer,
    is_match: bool,
) -> None:
    now = datetime.utcnow()
    game_round.status = models.RoundStatus.completed
    game_round.is_match = is_match
    game_round.completed_at = now
    db.add(models.CoupleQuestionHistory(couple_id=couple.id, question_id=game_round.question_id))

    answerer = db.query(models.User).filter(models.User.id == game_round.answerer_id).first()
    guesser = db.query(models.User).filter(models.User.id == game_round.guesser_id).first()

    points_awarded = MATCH_POINTS if is_match else 0
    coins_awarded = MATCH_COINS if is_match else NO_MATCH_COINS

    for u, resp_time in (
        (answerer, answerer_answer.response_time_seconds),
        (guesser, guess_answer.response_time_seconds),
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
        "question": _question_payload(question),
        "answers": [
            {"user_id": answerer.id, "text": answerer_answer.text, "selected_option_id": answerer_answer.selected_option_id},
            {"user_id": guesser.id, "text": guess_answer.text, "selected_option_id": guess_answer.selected_option_id},
        ],
        "answerer_id": answerer.id,
        "guesser_id": guesser.id,
        "is_match": is_match,
        "points_awarded": points_awarded,
        "coins_awarded": coins_awarded,
    }
    await manager.broadcast_to_couple(couple.id, result_payload)

    for u, resp_time in (
        (answerer, answerer_answer.response_time_seconds),
        (guesser, guess_answer.response_time_seconds),
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
