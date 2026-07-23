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
import type { WsServerMessage, AnswerOut } from "@/types";

type RoundState =
  | { phase: "idle" }
  | {
      phase: "in_progress";
      roundId: number;
      question: { id: number; text: string; category: string };
      firstResponderId: string;
      secondResponderId: string;
      myTurn: boolean;
      iAnswered: boolean;
    }
  | {
      phase: "result";
      roundId: number;
      question: { id: number; text: string; category: string };
      answers: AnswerOut[];
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

  const handleMessage = useCallback(
    (msg: WsServerMessage) => {
      switch (msg.action) {
        case "round_started": {
          const uid = getUserId() || "";
          setRatingSubmitted(false);
          setRound({
            phase: "in_progress",
            roundId: msg.round_id,
            question: msg.question,
            firstResponderId: msg.first_responder_id,
            secondResponderId: msg.second_responder_id,
            myTurn: msg.first_responder_id === uid,
            iAnswered: false,
          });
          break;
        }
        case "answer_saved": {
          setRound((prev) =>
            prev.phase === "in_progress" ? { ...prev, iAnswered: true, myTurn: false } : prev
          );
          break;
        }
        case "your_turn": {
          setRound((prev) => (prev.phase === "in_progress" ? { ...prev, myTurn: true } : prev));
          break;
        }
        case "round_result": {
          setRound({
            phase: "result",
            roundId: msg.round_id,
            question: msg.question,
            answers: msg.answers,
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
    },
    []
  );

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

  function submitAnswer(text: string) {
    if (round.phase !== "in_progress") return;
    socketRef.current?.send({ action: "submit_answer", round_id: round.roundId, text });
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

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Вопросы для пары 💞</h1>
        <div className="flex items-center gap-3 text-sm">
          {coins !== null && <span className="font-semibold text-yellow-500">🪙 {coins}</span>}
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
          <p className="text-gray-500">Готовы узнать друг друга получше?</p>
          <button className="btn-primary" onClick={startRound} disabled={status !== "open"}>
            Начать раунд
          </button>
        </div>
      )}

      {round.phase === "in_progress" && (
        <div className="space-y-4">
          <QuestionCard text={round.question.text} category={round.question.category} />
          {round.myTurn ? (
            <AnswerInput disabled={false} onSubmit={submitAnswer} />
          ) : round.iAnswered ? (
            <p className="text-center text-gray-500">
              Ваш ответ сохранён. Ждём, пока партнёр тоже ответит...
            </p>
          ) : (
            <p className="text-center text-gray-500">
              Сейчас отвечает партнёр. Как только он закончит, придёт ваша очередь.
            </p>
          )}
        </div>
      )}

      {round.phase === "result" && (
        <ResultModal
          questionText={round.question.text}
          answers={round.answers}
          myUserId={myUserId}
          isMatch={round.isMatch}
          pointsAwarded={round.pointsAwarded}
          coinsAwarded={round.coinsAwarded}
          onRate={handleRate}
          onReport={handleReport}
          ratingSubmitted={ratingSubmitted}
          onNextRound={handleNextRound}
        />
      )}

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
