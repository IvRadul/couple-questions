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

# Сколько вопросов приходится на каждого игрока за одну игровую сессию
# (сессия = несколько раундов подряд по одному паку, роль "отвечающего"
# строго чередуется). Итоговое число раундов в сессии — 2 * это значение,
# но не больше, чем реально доступно вопросов в паке (см. _start_new_session).
QUESTIONS_PER_PLAYER = 3


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
# Перед игрой один из партнёров выбирает пак вопросов и предлагает сыграть
# именно в него — второй партнёр должен принять или отклонить предложение.
# После принятия создаётся ИГРОВАЯ СЕССИЯ (GameSession) из нескольких
# раундов подряд (по умолчанию QUESTIONS_PER_PLAYER вопросов на каждого
# игрока, роль "отвечающего" строго чередуется). Раунды идут один за
# другим — после каждого показывается его результат, а после последнего
# раунда сессии — общий итог (session_completed).
#
# Роли внутри каждого раунда:
#   answerer — отвечает на вопрос "про себя".
#   guesser  — пытается угадать ответ партнёра, не видя его.
#
# Оба отвечают ОДНОВРЕМЕННО и независимо — guesser в любом случае не видит
# ответ answerer'а, пока сам не ответит, так что ждать друг друга не нужно.
# Раунд переходит к разрешению, как только ответили ОБА (независимо от
# порядка).
#
# Разрешение раунда зависит от типа вопроса:
#   question_type == "choice" -> сравнение вариантов автоматическое.
#   question_type == "open"   -> после того как оба ответили, решение о
#                                  совпадении принимает вручную answerer
#                                  (кнопка validate_answer).
#
# Протокол (JSON-сообщения):
#   Клиент -> Сервер:
#     {"action": "propose_round", "pack_id": 1}
#     {"action": "respond_round_proposal", "pack_id": 1, "accept": true}
#     {"action": "submit_answer", "round_id": 1, "text": "...", "option_id": null}
#     {"action": "validate_answer", "round_id": 1, "is_match": true}
#     {"action": "next_round"}   -> перейти к следующему вопросу сессии
#
#   Сервер -> Клиент(ы):
#     {"action": "round_proposed", "pack_id", "pack_name", "proposer_id"}
#     {"action": "round_declined", "pack_id"}
#     {"action": "round_started", "round_id", "question", "answerer_id", "guesser_id",
#      "session_progress": {"sequence_number", "total_rounds"}}
#     {"action": "answer_saved", "round_id"}
#     {"action": "partner_answered", "round_id"}
#     {"action": "awaiting_validation", "round_id"}
#     {"action": "validate_request", "round_id", "your_answer", "guess"}
#     {"action": "round_result", "round_id", "question", "answers", "answerer_id",
#      "guesser_id", "is_match", "points_awarded", "coins_awarded",
#      "session_progress": {"sequence_number", "total_rounds"}}
#     {"action": "session_completed", "session_id", "total_rounds", "matches",
#      "total_points", "total_coins"}
#     {"action": "new_achievement", "achievement": {...}}
#     {"action": "error", "detail": "..."}
#
# Предложение раунда (propose_round/round_proposed) не хранится в БД — это
# лёгкий, недолговечный обмен: если партнёр в этот момент не подключён к
# WebSocket, сообщение теряется, как и обычные уведомления о ходе;
# повторное предложение решает эту ситуацию. Сама игровая сессия и её
# раунды, наоборот, полностью хранятся в БД, поэтому переподключение
# посреди сессии (в том числе между раундами, пока никто не нажал "дальше")
# корректно восстанавливает состояние.
# --------------------------------------------------------------------------

def _question_payload(question: models.Question, answerer_display_name: Optional[str]) -> dict:
    return {
        "id": question.id,
        "text": crud.render_question_text(question.text, answerer_display_name),
        "category": question.category,
        "question_type": question.question_type.value,
        "options": [{"id": o.id, "text": o.text} for o in question.options],
    }


def _session_progress_payload(game_round: models.GameRound) -> Optional[dict]:
    if game_round.session_id is None:
        return None
    return {
        "sequence_number": game_round.sequence_number,
        "total_rounds": game_round.session.total_rounds,
    }


def _round_result_payload(
    game_round: models.GameRound,
    answerer: models.User,
    answerer_answer: models.Answer,
    guesser: models.User,
    guesser_answer: models.Answer,
    points_awarded: int,
    coins_awarded: int,
) -> dict:
    return {
        "action": "round_result",
        "round_id": game_round.id,
        "question": _question_payload(game_round.question, answerer.display_name),
        "answers": [
            {"user_id": answerer.id, "text": answerer_answer.text, "selected_option_id": answerer_answer.selected_option_id},
            {"user_id": guesser.id, "text": guesser_answer.text, "selected_option_id": guesser_answer.selected_option_id},
        ],
        "answerer_id": answerer.id,
        "guesser_id": guesser.id,
        "is_match": bool(game_round.is_match),
        "points_awarded": points_awarded,
        "coins_awarded": coins_awarded,
        "session_progress": _session_progress_payload(game_round),
    }


def _session_summary_payload(session: models.GameSession) -> dict:
    completed_rounds = [r for r in session.rounds if r.status == models.RoundStatus.completed]
    matches = sum(1 for r in completed_rounds if r.is_match)
    total_points = matches * MATCH_POINTS
    total_coins = sum(MATCH_COINS if r.is_match else NO_MATCH_COINS for r in completed_rounds)
    return {
        "action": "session_completed",
        "session_id": session.id,
        "total_rounds": session.total_rounds,
        "matches": matches,
        "total_points": total_points,
        "total_coins": total_coins,
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
            "question": _question_payload(game_round.question, game_round.answerer.display_name),
            "answerer_id": game_round.answerer_id,
            "guesser_id": game_round.guesser_id,
            "session_progress": _session_progress_payload(game_round),
        }
    ]

    if game_round.status == models.RoundStatus.in_progress:
        my_answer = next((a for a in game_round.answers if a.user_id == target_user_id), None)
        if my_answer is not None:
            messages.append({"action": "answer_saved", "round_id": game_round.id})
        elif len(game_round.answers) > 0:
            # Партнёр уже ответил, а этот клиент — ещё нет.
            messages.append({"action": "partner_answered", "round_id": game_round.id})

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
    if active_round is not None:
        for msg in _build_round_sync_messages(active_round, user_id):
            await manager.send_to_user(couple_id, user_id, msg)
        return

    # Ни одного активного раунда — возможно, сессия всё ещё идёт, но никто
    # ещё не запросил следующий вопрос (например, партнёр как раз посмотрел
    # результат и не успел нажать "дальше"). Восстановим последний
    # завершённый раунд сессии, чтобы клиент увидел актуальный прогресс и
    # кнопку "следующий вопрос" вместо пустого экрана выбора пака.
    session = (
        db.query(models.GameSession)
        .filter(
            models.GameSession.couple_id == couple_id,
            models.GameSession.status == models.SessionStatus.in_progress,
        )
        .order_by(models.GameSession.id.desc())
        .first()
    )
    if session is None:
        return

    last_round = (
        db.query(models.GameRound)
        .filter(models.GameRound.session_id == session.id, models.GameRound.status == models.RoundStatus.completed)
        .order_by(models.GameRound.sequence_number.desc())
        .first()
    )
    if last_round is None:
        return

    answerer = last_round.answerer
    guesser = last_round.guesser
    answerer_answer = next((a for a in last_round.answers if a.user_id == answerer.id), None)
    guesser_answer = next((a for a in last_round.answers if a.user_id == guesser.id), None)
    if answerer_answer is None or guesser_answer is None:
        return

    points_awarded = MATCH_POINTS if last_round.is_match else 0
    coins_awarded = MATCH_COINS if last_round.is_match else NO_MATCH_COINS
    await manager.send_to_user(
        couple_id,
        user_id,
        _round_result_payload(last_round, answerer, answerer_answer, guesser, guesser_answer, points_awarded, coins_awarded),
    )


@router.websocket("/ws/{couple_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    couple_id: str,
    token: str = Query(...),
):
    # Принимаем соединение сразу, независимо от исхода последующей валидации —
    # так клиент (и nginx между ним и backend'ом) всегда видят корректный
    # HTTP 101 хендшейк, а не обрыв соединения на середине апгрейда. Некоторые
    # связки nginx+ASGI отдают такой обрыв клиенту как 502 Bad Gateway вместо
    # понятной ошибки — closing до accept() формально валиден по ASGI, но
    # на практике не везде проксируется чисто.
    await websocket.accept()

    db = SessionLocal()
    try:
        user = decode_token_for_ws(token, db)
        if user is None or user.couple_id != couple_id:
            await websocket.send_json(
                {"action": "error", "detail": "Сессия недействительна — обновите страницу"}
            )
            await websocket.close(code=4401)
            return

        couple = db.query(models.Couple).filter(models.Couple.id == couple_id).first()
        if couple is None or couple.status != models.CoupleStatus.active:
            await websocket.send_json(
                {"action": "error", "detail": "Эта пара сейчас недоступна — обновите страницу"}
            )
            await websocket.close(code=4404)
            return

        await manager.connect(couple_id, user.id, websocket)

        # Если в паре уже идёт раунд/сессия (например, партнёр начал её раньше,
        # чем этот клиент успел подключиться), сразу подгружаем состояние —
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
                elif action == "next_round":
                    await _handle_next_round(db, couple, user, message)
                else:
                    await manager.send_to_user(
                        couple_id, user.id, {"action": "error", "detail": f"Неизвестное действие: {action}"}
                    )
        except WebSocketDisconnect:
            manager.disconnect(couple_id, user.id)
    finally:
        db.close()


def _has_active_round(db: Session, couple_id: str) -> bool:
    return (
        db.query(models.GameRound)
        .filter(
            models.GameRound.couple_id == couple_id,
            models.GameRound.status != models.RoundStatus.completed,
        )
        .first()
        is not None
    )


async def _handle_propose_round(db: Session, couple: models.Couple, proposer: models.User, message: dict) -> None:
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

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if any(not m.display_name for m in members):
        # Имя обязательно (подставляется в текст вопросов вместо "партнёр") —
        # фронтенд не должен пускать сюда без него, но подстрахуемся и здесь.
        await manager.send_to_user(
            couple.id,
            proposer.id,
            {"action": "error", "detail": "Оба участника пары должны указать имя, прежде чем начать игру"},
        )
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

    if crud.count_available_questions(db, couple.id, pack.id) == 0:
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

    # Не даём создать дубликат сессии/раунда, если он уже успел появиться
    # (например, из-за повторного клика "Принять" в двух вкладках).
    if _has_active_round(db, couple.id):
        active_round = (
            db.query(models.GameRound)
            .filter(
                models.GameRound.couple_id == couple.id,
                models.GameRound.status != models.RoundStatus.completed,
            )
            .first()
        )
        for msg in _build_round_sync_messages(active_round, responder.id):
            await manager.send_to_user(couple.id, responder.id, msg)
        return

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    if len(members) != 2:
        await manager.send_to_user(
            couple.id, responder.id, {"action": "error", "detail": "В паре должно быть двое участников"}
        )
        return

    pack = db.query(models.QuestionPack).filter(models.QuestionPack.id == pack_id).first()
    if pack is None:
        await manager.send_to_user(couple.id, responder.id, {"action": "error", "detail": "Пак не найден"})
        return

    available = crud.count_available_questions(db, couple.id, pack.id)
    if available == 0:
        await manager.broadcast_to_couple(
            couple.id,
            {"action": "error", "detail": "Вопросы в этом паке закончились, выберите другой пак"},
        )
        return

    total_rounds = min(2 * QUESTIONS_PER_PLAYER, available)
    if total_rounds > 1 and total_rounds % 2 == 1:
        total_rounds -= 1  # чётное число раундов — поровну на каждого игрока

    first_answerer, _ = random.sample(members, 2)

    session = models.GameSession(
        couple_id=couple.id,
        pack_id=pack.id,
        total_rounds=total_rounds,
        first_answerer_id=first_answerer.id,
        status=models.SessionStatus.in_progress,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    await _start_next_round_in_session(db, couple, session)


async def _start_next_round_in_session(db: Session, couple: models.Couple, session: models.GameSession) -> None:
    completed_count = (
        db.query(models.GameRound)
        .filter(models.GameRound.session_id == session.id, models.GameRound.status == models.RoundStatus.completed)
        .count()
    )
    if completed_count >= session.total_rounds:
        return  # сессия уже завершена — вызывающий код не должен был сюда попасть

    sequence_number = completed_count + 1

    members = db.query(models.User).filter(models.User.couple_id == couple.id).all()
    first = next((m for m in members if m.id == session.first_answerer_id), None)
    second = next((m for m in members if m.id != session.first_answerer_id), None)
    if first is None or second is None:
        await manager.broadcast_to_couple(
            couple.id, {"action": "error", "detail": "В паре должно быть двое участников"}
        )
        return

    # Роль "отвечающего" строго чередуется от раунда к раунду сессии.
    answerer, guesser = (first, second) if (sequence_number - 1) % 2 == 0 else (second, first)

    used_question_ids = [r.question_id for r in session.rounds]
    question = crud.pick_random_question(db, couple.id, pack_id=session.pack_id, exclude_ids=used_question_ids)
    if question is None:
        # Вопросы в паке кончились раньше, чем рассчитывали (гонка с другой
        # сессией и т.п.) — завершаем сессию тем, что успели сыграть.
        session.total_rounds = completed_count
        session.status = models.SessionStatus.completed
        session.completed_at = datetime.utcnow()
        db.commit()
        if completed_count > 0:
            await manager.broadcast_to_couple(couple.id, _session_summary_payload(session))
        else:
            await manager.broadcast_to_couple(
                couple.id, {"action": "error", "detail": "В этом паке не осталось новых вопросов"}
            )
        return

    game_round = models.GameRound(
        couple_id=couple.id,
        question_id=question.id,
        session_id=session.id,
        sequence_number=sequence_number,
        answerer_id=answerer.id,
        guesser_id=guesser.id,
        status=models.RoundStatus.in_progress,
    )
    db.add(game_round)
    db.commit()
    db.refresh(game_round)

    payload = {
        "action": "round_started",
        "round_id": game_round.id,
        "question": _question_payload(question, answerer.display_name),
        "answerer_id": answerer.id,
        "guesser_id": guesser.id,
        "session_progress": _session_progress_payload(game_round),
    }
    await manager.broadcast_to_couple(couple.id, payload)


async def _handle_next_round(db: Session, couple: models.Couple, user: models.User, message: dict) -> None:
    if _has_active_round(db, couple.id):
        active_round = (
            db.query(models.GameRound)
            .filter(
                models.GameRound.couple_id == couple.id,
                models.GameRound.status != models.RoundStatus.completed,
            )
            .first()
        )
        for msg in _build_round_sync_messages(active_round, user.id):
            await manager.send_to_user(couple.id, user.id, msg)
        return

    session = (
        db.query(models.GameSession)
        .filter(
            models.GameSession.couple_id == couple.id,
            models.GameSession.status == models.SessionStatus.in_progress,
        )
        .order_by(models.GameSession.id.desc())
        .first()
    )
    if session is None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Нет активной игровой сессии"})
        return

    await _start_next_round_in_session(db, couple, session)


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

    if user.id not in (game_round.answerer_id, game_round.guesser_id):
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Вы не участвуете в этом раунде"})
        return

    if game_round.status != models.RoundStatus.in_progress:
        await manager.send_to_user(
            couple.id, user.id, {"action": "error", "detail": "Раунд уже не принимает ответы"}
        )
        return

    already_answered = (
        db.query(models.Answer)
        .filter(models.Answer.round_id == game_round.id, models.Answer.user_id == user.id)
        .first()
    )
    if already_answered is not None:
        await manager.send_to_user(couple.id, user.id, {"action": "error", "detail": "Вы уже ответили в этом раунде"})
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
    # Оба отвечают одновременно и независимо, поэтому время ответа меряем от
    # одной и той же точки отсчёта для обоих — от старта раунда.
    response_time = int((now - game_round.created_at).total_seconds())

    answer = models.Answer(
        round_id=game_round.id,
        user_id=user.id,
        text=text,
        selected_option_id=selected_option.id if selected_option else None,
        response_time_seconds=response_time,
    )
    db.add(answer)
    db.commit()

    await manager.send_to_user(couple.id, user.id, {"action": "answer_saved", "round_id": game_round.id})

    answerer_answer = (
        db.query(models.Answer)
        .filter(models.Answer.round_id == game_round.id, models.Answer.user_id == game_round.answerer_id)
        .first()
    )
    guesser_answer = (
        db.query(models.Answer)
        .filter(models.Answer.round_id == game_round.id, models.Answer.user_id == game_round.guesser_id)
        .first()
    )

    if answerer_answer is None or guesser_answer is None:
        # Партнёр ещё не ответил — просто уведомляем его, что первый ответ уже готов.
        other_id = game_round.guesser_id if user.id == game_round.answerer_id else game_round.answerer_id
        await manager.send_to_user(couple.id, other_id, {"action": "partner_answered", "round_id": game_round.id})
        return

    # Ответили оба — переходим к разрешению раунда.
    if question.question_type == models.QuestionType.choice:
        is_match = (
            answerer_answer.selected_option_id is not None
            and answerer_answer.selected_option_id == guesser_answer.selected_option_id
        )
        await _finalize_round(db, couple, game_round, answerer_answer, guesser_answer, is_match)
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
                "guess": guesser_answer.text,
            },
        )
        await manager.send_to_user(
            couple.id, game_round.guesser_id, {"action": "awaiting_validation", "round_id": game_round.id}
        )


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
    db.refresh(game_round)

    result_payload = _round_result_payload(
        game_round, answerer, answerer_answer, guesser, guess_answer, points_awarded, coins_awarded
    )
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

    # Если это был последний раунд сессии — сразу подводим общий итог.
    if game_round.session_id is not None:
        session = game_round.session
        completed_count = (
            db.query(models.GameRound)
            .filter(models.GameRound.session_id == session.id, models.GameRound.status == models.RoundStatus.completed)
            .count()
        )
        if completed_count >= session.total_rounds and session.status != models.SessionStatus.completed:
            session.status = models.SessionStatus.completed
            session.completed_at = datetime.utcnow()
            db.commit()
            await manager.broadcast_to_couple(couple.id, _session_summary_payload(session))
