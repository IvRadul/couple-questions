"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ensureAuthenticated, getCoupleId, getUserId } from "@/lib/auth";
import { connectGameSocket } from "@/lib/websocket";
import { api } from "@/lib/api";
import QuestionCard from "@/components/QuestionCard";
import AnswerInput from "@/components/AnswerInput";
import ResultModal from "@/components/ResultModal";
import AchievementToast from "@/components/AchievementToast";
import ValidationPanel from "@/components/ValidationPanel";
import type { WsServerMessage, AnswerOut, RoundQuestionPayload, PackOut } from "@/types";

type RoundStatus = "waiting_answer" | "waiting_guess" | "waiting_validation";

type GameState =
  | { phase: "idle" }
  | { phase: "invite_sent"; packId: number; packName: string }
  | { phase: "invite_received"; packId: number; packName: string; proposerId: string }
  | {
      phase: "in_progress";
      roundId: number;
      question: RoundQuestionPayload;
      answererId: string;
      guesserId: string;
      status: RoundStatus;
      validation?: { yourAnswer: string; guess: string };
    }
  | {
      phase: "result";
      roundId: number;
      question: RoundQuestionPayload;
      answers: AnswerOut[];
      answererId: string;
      guesserId: string;
      isMatch: boolean;
      pointsAwarded: number;
      coinsAwarded: number;
    };

interface AchievementPopup {
  code: string;
  title: string;
  description: string;
  coin_reward: number;
}

export default function GamePage() {
  const router = useRouter();
  const socketRef = useRef<ReturnType<typeof connectGameSocket> | null>(null);

  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [game, setGame] = useState<GameState>({ phase: "idle" });
  const [myUserId, setMyUserId] = useState<string>("");
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [achievementQueue, setAchievementQueue] = useState<AchievementPopup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [coins, setCoins] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [unlockedPacks, setUnlockedPacks] = useState<PackOut[]>([]);
  const [packsLoading, setPacksLoading] = useState(true);

  const handleMessage = useCallback((msg: WsServerMessage) => {
    switch (msg.action) {
      case "round_proposed": {
        const uid = getUserId() || "";
        if (msg.proposer_id === uid) {
          setGame({ phase: "invite_sent", packId: msg.pack_id, packName: msg.pack_name });
        } else {
          setGame({
            phase: "invite_received",
            packId: msg.pack_id,
            packName: msg.pack_name,
            proposerId: msg.proposer_id,
          });
        }
        break;
      }
      case "round_declined": {
        setError("Партнёр отклонил игру с этим паком — выберите другой.");
        setGame({ phase: "idle" });
        break;
      }
      case "round_started": {
        setRatingSubmitted(false);
        setGame({
          phase: "in_progress",
          roundId: msg.round_id,
          question: msg.question,
          answererId: msg.answerer_id,
          guesserId: msg.guesser_id,
          status: "waiting_answer",
        });
        break;
      }
      case "answer_saved": {
        setGame((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_guess" } : prev));
        break;
      }
      case "your_turn": {
        setGame((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_guess" } : prev));
        break;
      }
      case "awaiting_validation": {
        setGame((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_validation" } : prev));
        break;
      }
      case "validate_request": {
        setGame((prev) =>
          prev.phase === "in_progress"
            ? {
                ...prev,
                status: "waiting_validation",
                validation: { yourAnswer: msg.your_answer, guess: msg.guess },
              }
            : prev
        );
        break;
      }
      case "round_result": {
        setGame({
          phase: "result",
          roundId: msg.round_id,
          question: msg.question,
          answers: msg.answers,
          answererId: msg.answerer_id,
          guesserId: msg.guesser_id,
          isMatch: msg.is_match,
          pointsAwarded: msg.points_awarded,
          coinsAwarded: msg.coins_awarded,
        });
        break;
      }
      case "new_achievement": {
        setAchievementQueue((prev) => [...prev, msg.achievement]);
        break;
      }
      case "error": {
        setError(msg.detail);
        break;
      }
    }
  }, []);

  async function loadPacks() {
    setPacksLoading(true);
    try {
      const packs = await api.getPacks();
      setUnlockedPacks(packs.filter((p) => p.unlocked));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPacksLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();
      const coupleId = getCoupleId();
      if (!coupleId) {
        router.replace("/couple");
        return;
      }
      setMyUserId(getUserId() || "");

      try {
        const me = await api.me();
        if (!me.display_name) {
          router.replace("/welcome");
          return;
        }
        setCoins(me.coins);
      } catch {
        // не критично для запуска игры — просто не покажем баланс монет
      }

      await loadPacks();

      socketRef.current = connectGameSocket(coupleId, handleMessage, setStatus);
    })();

    return () => {
      socketRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function proposePack(pack: PackOut) {
    setError(null);
    socketRef.current?.send({ action: "propose_round", pack_id: pack.id });
    // Оптимистично переходим в состояние "ждём ответа" — сервер подтвердит через round_proposed
    setGame({ phase: "invite_sent", packId: pack.id, packName: pack.name });
  }

  function respondToInvite(accept: boolean) {
    if (game.phase !== "invite_received") return;
    socketRef.current?.send({ action: "respond_round_proposal", pack_id: game.packId, accept });
    if (!accept) {
      setGame({ phase: "idle" });
    }
  }

  function submitTextAnswer(text: string) {
    if (game.phase !== "in_progress") return;
    socketRef.current?.send({ action: "submit_answer", round_id: game.roundId, text });
  }

  function submitOptionAnswer(optionId: number, text: string) {
    if (game.phase !== "in_progress") return;
    socketRef.current?.send({ action: "submit_answer", round_id: game.roundId, text, option_id: optionId });
  }

  function submitValidation(isMatch: boolean) {
    if (game.phase !== "in_progress") return;
    socketRef.current?.send({ action: "validate_answer", round_id: game.roundId, is_match: isMatch });
  }

  async function handleRate(stars: number) {
    if (game.phase !== "result") return;
    try {
      await api.rateQuestion({ question_id: game.question.id, round_id: game.roundId, stars });
      setRatingSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleReport() {
    if (game.phase !== "result") return;
    try {
      await api.rateQuestion({ question_id: game.question.id, round_id: game.roundId, is_report: true });
      setRatingSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleNextRound() {
    setGame({ phase: "idle" });
    // Баланс мог измениться по итогам раунда (и если использовался пак с ценой) — обновим паки/монеты
    try {
      const me = await api.me();
      setCoins(me.coins);
    } catch {
      // не критично
    }
    loadPacks();
  }

  async function handleLeaveCouple() {
    if (leaving) return;
    const confirmed = window.confirm(
      "Расформировать текущую пару и создать новую? Ваши монеты и достижения сохранятся."
    );
    if (!confirmed) return;
    setLeaving(true);
    try {
      await api.leaveCouple();
      socketRef.current?.close();
      router.replace("/couple");
    } catch (e: any) {
      setError(e.message);
      setLeaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Вопросы для пары 💞</h1>
        <div className="flex items-center gap-3 text-sm">
          {coins !== null && <span className="font-semibold text-yellow-500">🪙 {coins}</span>}
          <Link href="/packs" className="text-primary underline">
            Паки
          </Link>
          <Link href="/history" className="text-primary underline">
            История
          </Link>
          <Link href="/account" className="text-primary underline">
            Аккаунт
          </Link>
        </div>
      </header>

      {status !== "open" && (
        <p className="text-center text-sm text-gray-400">
          {status === "connecting" ? "Подключение..." : "Соединение потеряно, обновите страницу"}
        </p>
      )}

      {error && <p className="text-center text-sm text-red-500">{error}</p>}

      {game.phase === "idle" && (
        <PackPicker packs={unlockedPacks} loading={packsLoading} disabled={status !== "open"} onPick={proposePack} />
      )}

      {game.phase === "invite_sent" && (
        <div className="card text-center space-y-2">
          <p className="text-gray-500">
            Предложили партнёру сыграть в пак <span className="font-semibold">«{game.packName}»</span>
          </p>
          <p className="text-sm text-gray-400">Ждём ответа...</p>
        </div>
      )}

      {game.phase === "invite_received" && (
        <div className="card text-center space-y-3">
          <p className="text-gray-500">
            Партнёр предлагает сыграть в пак <span className="font-semibold">«{game.packName}»</span>
          </p>
          <div className="flex gap-3">
            <button
              className="flex-1 rounded-xl bg-green-500 text-white font-semibold py-3 hover:bg-green-600 transition"
              onClick={() => respondToInvite(true)}
            >
              Принять
            </button>
            <button
              className="flex-1 rounded-xl bg-gray-300 text-gray-700 font-semibold py-3 hover:bg-gray-400 transition"
              onClick={() => respondToInvite(false)}
            >
              Отклонить
            </button>
          </div>
        </div>
      )}

      {game.phase === "in_progress" && (
        <RoundView
          round={game}
          myUserId={myUserId}
          onSubmitText={submitTextAnswer}
          onSubmitOption={submitOptionAnswer}
          onValidate={submitValidation}
        />
      )}

      {game.phase === "result" && (
        <ResultModal
          questionText={game.question.text}
          answers={game.answers}
          myUserId={myUserId}
          answererId={game.answererId}
          isMatch={game.isMatch}
          pointsAwarded={game.pointsAwarded}
          coinsAwarded={game.coinsAwarded}
          onRate={handleRate}
          onReport={handleReport}
          ratingSubmitted={ratingSubmitted}
          onNextRound={handleNextRound}
        />
      )}

      <div className="text-center">
        <button
          onClick={handleLeaveCouple}
          disabled={leaving}
          className="text-xs text-gray-400 underline hover:text-red-500"
        >
          Расформировать пару и создать новую
        </button>
      </div>

      {achievementQueue.map((ach, idx) => (
        <AchievementToast
          key={`${ach.code}-${idx}`}
          title={ach.title}
          description={ach.description}
          coinReward={ach.coin_reward}
          onClose={() => setAchievementQueue((prev) => prev.filter((_, i) => i !== idx))}
        />
      ))}
    </div>
  );
}

function PackPicker({
  packs,
  loading,
  disabled,
  onPick,
}: {
  packs: PackOut[];
  loading: boolean;
  disabled: boolean;
  onPick: (pack: PackOut) => void;
}) {
  if (loading) {
    return <p className="text-center text-gray-400">Загрузка паков...</p>;
  }

  if (packs.length === 0) {
    return (
      <div className="card text-center space-y-2">
        <p className="text-gray-500">У вашей пары пока нет доступных паков вопросов.</p>
        <Link href="/packs" className="text-primary underline text-sm">
          Открыть паки
        </Link>
      </div>
    );
  }

  return (
    <div className="card space-y-3">
      <p className="text-center text-gray-500">Выберите пак и предложите партнёру сыграть</p>
      <div className="flex flex-col gap-2">
        {packs.map((pack) => (
          <button
            key={pack.id}
            disabled={disabled}
            onClick={() => onPick(pack)}
            className="w-full text-left rounded-xl border border-gray-300 px-4 py-3 transition hover:border-primary hover:bg-primary-light/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="font-medium">{pack.name}</span>
            <span className="block text-xs text-gray-400">{pack.question_count} вопросов</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function RoundView({
  round,
  myUserId,
  onSubmitText,
  onSubmitOption,
  onValidate,
}: {
  round: Extract<GameState, { phase: "in_progress" }>;
  myUserId: string;
  onSubmitText: (text: string) => void;
  onSubmitOption: (optionId: number, text: string) => void;
  onValidate: (isMatch: boolean) => void;
}) {
  const iAmAnswerer = myUserId === round.answererId;
  const roleLabel = iAmAnswerer
    ? "Вы отвечаете на вопрос за себя"
    : "Вы пытаетесь угадать ответ партнёра";

  return (
    <div className="space-y-4">
      <QuestionCard
        text={round.question.text}
        category={round.question.category}
        questionType={round.question.question_type}
        roleLabel={roleLabel}
      />

      {round.status === "waiting_answer" && iAmAnswerer && (
        <AnswerInput
          questionType={round.question.question_type}
          options={round.question.options}
          disabled={false}
          onSubmitText={onSubmitText}
          onSubmitOption={onSubmitOption}
          placeholder="Как бы вы сами ответили на этот вопрос?"
        />
      )}

      {round.status === "waiting_answer" && !iAmAnswerer && (
        <p className="text-center text-gray-500">Партнёр сейчас отвечает на вопрос про себя...</p>
      )}

      {round.status === "waiting_guess" && !iAmAnswerer && (
        <AnswerInput
          questionType={round.question.question_type}
          options={round.question.options}
          disabled={false}
          onSubmitText={onSubmitText}
          onSubmitOption={onSubmitOption}
          placeholder="Как вы думаете, что ответил партнёр?"
        />
      )}

      {round.status === "waiting_guess" && iAmAnswerer && (
        <p className="text-center text-gray-500">
          Ваш ответ сохранён. Партнёр сейчас пытается угадать его...
        </p>
      )}

      {round.status === "waiting_validation" && iAmAnswerer && round.validation && (
        <ValidationPanel
          yourAnswer={round.validation.yourAnswer}
          guess={round.validation.guess}
          onValidate={onValidate}
        />
      )}

      {round.status === "waiting_validation" && !iAmAnswerer && (
        <p className="text-center text-gray-500">
          Партнёр сверяет вашу догадку со своим ответом, подождите немного...
        </p>
      )}
    </div>
  );
}
