"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ensureAuthenticated, getUserId, getToken, saveSession, clearCoupleId } from "@/lib/auth";
import { connectGameSocket } from "@/lib/websocket";
import { api } from "@/lib/api";
import QuestionCard from "@/components/QuestionCard";
import AnswerInput from "@/components/AnswerInput";
import ResultModal from "@/components/ResultModal";
import AchievementToast from "@/components/AchievementToast";
import ValidationPanel from "@/components/ValidationPanel";
import RoleBanner from "@/components/RoleBanner";
import SessionSummary from "@/components/SessionSummary";
import type { WsServerMessage, AnswerOut, RoundQuestionPayload, PackOut, SessionProgress } from "@/types";

type RoundStatus = "in_progress" | "waiting_validation";

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
      mySubmitted: boolean;
      partnerAnswered: boolean;
      validation?: { yourAnswer: string; guess: string };
      sessionProgress: SessionProgress | null;
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
      sessionProgress: SessionProgress | null;
    }
  | {
      phase: "session_summary";
      totalRounds: number;
      matches: number;
      totalPoints: number;
      totalCoins: number;
    };

interface AchievementPopup {
  code: string;
  title: string;
  description: string;
  coin_reward: number;
}

interface PendingSessionSummary {
  totalRounds: number;
  matches: number;
  totalPoints: number;
  totalCoins: number;
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
  const [unlockedPacks, setUnlockedPacks] = useState<PackOut[]>([]);
  const [packsLoading, setPacksLoading] = useState(true);
  const [pendingSummary, setPendingSummary] = useState<PendingSessionSummary | null>(null);
  const [advancing, setAdvancing] = useState(false);

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
        setPendingSummary(null);
        setAdvancing(false);
        setGame({
          phase: "in_progress",
          roundId: msg.round_id,
          question: msg.question,
          answererId: msg.answerer_id,
          guesserId: msg.guesser_id,
          status: "in_progress",
          mySubmitted: false,
          partnerAnswered: false,
          sessionProgress: msg.session_progress,
        });
        break;
      }
      case "answer_saved": {
        setGame((prev) => (prev.phase === "in_progress" ? { ...prev, mySubmitted: true } : prev));
        break;
      }
      case "partner_answered": {
        setGame((prev) => (prev.phase === "in_progress" ? { ...prev, partnerAnswered: true } : prev));
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
        setAdvancing(false);
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
          sessionProgress: msg.session_progress,
        });
        break;
      }
      case "session_completed": {
        // Приходит сразу после round_result для последнего раунда сессии.
        // Не переключаем фазу сразу — даём посмотреть результат последнего
        // вопроса и оценить его, итог покажем по кнопке "Посмотреть итоги".
        setPendingSummary({
          totalRounds: msg.total_rounds,
          matches: msg.matches,
          totalPoints: msg.total_points,
          totalCoins: msg.total_coins,
        });
        break;
      }
      case "new_achievement": {
        setAchievementQueue((prev) => [...prev, msg.achievement]);
        break;
      }
      case "couple_disbanded": {
        socketRef.current?.close();
        clearCoupleId();
        router.replace("/couple");
        break;
      }
      case "error": {
        setAdvancing(false);
        setError(msg.detail);
        break;
      }
    }
  }, [router]);

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

      let me;
      try {
        me = await api.me();
      } catch (e: any) {
        // Не смогли подтвердить личность/статус пользователя — не пускаем
        // дальше ни при каких обстоятельствах (fail-closed), а не молча
        // продолжаем с устаревшими локальными данными.
        setError(e.message || "Не удалось подключиться к серверу");
        return;
      }

      // Держим localStorage в согласии с сервером — на случай, если пара
      // была расформирована партнёром (couple_disbanded) или изменилась
      // как-то ещё, пока эта вкладка была неактивна.
      const token = getToken();
      if (token) {
        saveSession(token, me.id, me.couple_id);
      }

      if (!me.display_name) {
        router.replace("/welcome");
        return;
      }
      setCoins(me.coins);
      setMyUserId(me.id);

      if (!me.couple_id) {
        router.replace("/couple");
        return;
      }

      await loadPacks();

      socketRef.current = connectGameSocket(me.couple_id, handleMessage, setStatus);
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

  function handleNextRound() {
    if (pendingSummary) {
      setGame({ phase: "session_summary", ...pendingSummary });
      setPendingSummary(null);
      return;
    }
    setAdvancing(true);
    socketRef.current?.send({ action: "next_round" });
  }

  async function handleSessionDone() {
    setGame({ phase: "idle" });
    try {
      const me = await api.me();
      setCoins(me.coins);
    } catch {
      // не критично
    }
    loadPacks();
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
        <>
          {advancing && (
            <p className="text-center text-sm text-gray-400">Загружаем следующий вопрос...</p>
          )}
          <ResultModal
            questionText={game.question.text}
            answers={game.answers}
            myUserId={myUserId}
            answererId={game.answererId}
            isMatch={game.isMatch}
            pointsAwarded={game.pointsAwarded}
            coinsAwarded={game.coinsAwarded}
            sessionProgress={game.sessionProgress}
            isLastInSession={pendingSummary !== null}
            onRate={handleRate}
            onReport={handleReport}
            ratingSubmitted={ratingSubmitted}
            onNextRound={handleNextRound}
          />
        </>
      )}

      {game.phase === "session_summary" && (
        <SessionSummary
          totalRounds={game.totalRounds}
          matches={game.matches}
          totalPoints={game.totalPoints}
          totalCoins={game.totalCoins}
          onDone={handleSessionDone}
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

  return (
    <div className="space-y-4">
      {round.sessionProgress && (
        <p className="text-center text-xs text-gray-400">
          Вопрос {round.sessionProgress.sequence_number} из {round.sessionProgress.total_rounds}
        </p>
      )}

      <RoleBanner role={iAmAnswerer ? "answerer" : "guesser"} />

      <QuestionCard
        text={round.question.text}
        category={round.question.category}
        questionType={round.question.question_type}
      />

      {round.status === "in_progress" && !round.mySubmitted && (
        <>
          {round.partnerAnswered && (
            <p className="text-center text-sm text-primary">
              Партнёр уже ответил — не заставляйте ждать 😄
            </p>
          )}
          <AnswerInput
            questionType={round.question.question_type}
            options={round.question.options}
            disabled={false}
            onSubmitText={onSubmitText}
            onSubmitOption={onSubmitOption}
            placeholder={
              iAmAnswerer
                ? "Как бы вы сами ответили на этот вопрос?"
                : "Как вы думаете, что ответит партнёр?"
            }
          />
        </>
      )}

      {round.status === "in_progress" && round.mySubmitted && (
        <p className="text-center text-gray-500">Ответ отправлен ✓ Ждём партнёра...</p>
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
