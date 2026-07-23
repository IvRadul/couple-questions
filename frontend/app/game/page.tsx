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
import type { WsServerMessage, AnswerOut, RoundQuestionPayload } from "@/types";

type RoundStatus = "waiting_answer" | "waiting_guess" | "waiting_validation";

type RoundState =
  | { phase: "idle" }
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
  const [round, setRound] = useState<RoundState>({ phase: "idle" });
  const [myUserId, setMyUserId] = useState<string>("");
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [achievementQueue, setAchievementQueue] = useState<AchievementPopup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [coins, setCoins] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);

  const handleMessage = useCallback((msg: WsServerMessage) => {
    switch (msg.action) {
      case "round_started": {
        setRatingSubmitted(false);
        setRound({
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
        setRound((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_guess" } : prev));
        break;
      }
      case "your_turn": {
        setRound((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_guess" } : prev));
        break;
      }
      case "awaiting_validation": {
        setRound((prev) => (prev.phase === "in_progress" ? { ...prev, status: "waiting_validation" } : prev));
        break;
      }
      case "validate_request": {
        setRound((prev) =>
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
        setRound({
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
        setCoins(me.coins);
      } catch {
        // не критично для запуска игры
      }

      socketRef.current = connectGameSocket(coupleId, handleMessage, setStatus);
    })();

    return () => {
      socketRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startRound() {
    setError(null);
    socketRef.current?.send({ action: "start_round" });
  }

  function submitTextAnswer(text: string) {
    if (round.phase !== "in_progress") return;
    socketRef.current?.send({ action: "submit_answer", round_id: round.roundId, text });
  }

  function submitOptionAnswer(optionId: number, text: string) {
    if (round.phase !== "in_progress") return;
    socketRef.current?.send({ action: "submit_answer", round_id: round.roundId, text, option_id: optionId });
  }

  function submitValidation(isMatch: boolean) {
    if (round.phase !== "in_progress") return;
    socketRef.current?.send({ action: "validate_answer", round_id: round.roundId, is_match: isMatch });
  }

  async function handleRate(stars: number) {
    if (round.phase !== "result") return;
    try {
      await api.rateQuestion({ question_id: round.question.id, round_id: round.roundId, stars });
      setRatingSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleReport() {
    if (round.phase !== "result") return;
    try {
      await api.rateQuestion({ question_id: round.question.id, round_id: round.roundId, is_report: true });
      setRatingSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  function handleNextRound() {
    setRound({ phase: "idle" });
    startRound();
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
        </div>
      </header>

      {status !== "open" && (
        <p className="text-center text-sm text-gray-400">
          {status === "connecting" ? "Подключение..." : "Соединение потеряно, обновите страницу"}
        </p>
      )}

      {error && <p className="text-center text-sm text-red-500">{error}</p>}

      {round.phase === "idle" && (
        <div className="card text-center space-y-3">
          <p className="text-gray-500">Готовы узнать друг друга получше???</p>
          <button className="btn-primary" onClick={startRound} disabled={status !== "open"}>
            Начать раунд
          </button>
        </div>
      )}

      {round.phase === "in_progress" && (
        <RoundView
          round={round}
          myUserId={myUserId}
          onSubmitText={submitTextAnswer}
          onSubmitOption={submitOptionAnswer}
          onValidate={submitValidation}
        />
      )}

      {round.phase === "result" && (
        <ResultModal
          questionText={round.question.text}
          answers={round.answers}
          myUserId={myUserId}
          answererId={round.answererId}
          isMatch={round.isMatch}
          pointsAwarded={round.pointsAwarded}
          coinsAwarded={round.coinsAwarded}
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

function RoundView({
  round,
  myUserId,
  onSubmitText,
  onSubmitOption,
  onValidate,
}: {
  round: Extract<RoundState, { phase: "in_progress" }>;
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
