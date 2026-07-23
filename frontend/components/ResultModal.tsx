"use client";

import RatingStars from "./RatingStars";
import type { AnswerOut } from "@/types";

interface Props {
  questionText: string;
  answers: AnswerOut[];
  myUserId: string;
  answererId: string;
  isMatch: boolean;
  pointsAwarded: number;
  coinsAwarded: number;
  onRate: (stars: number) => void;
  onReport: () => void;
  ratingSubmitted: boolean;
  onNextRound: () => void;
}

export default function ResultModal({
  questionText,
  answers,
  myUserId,
  answererId,
  isMatch,
  pointsAwarded,
  coinsAwarded,
  onRate,
  onReport,
  ratingSubmitted,
  onNextRound,
}: Props) {
  const answererAnswer = answers.find((a) => a.user_id === answererId);
  const guesserAnswer = answers.find((a) => a.user_id !== answererId);
  const iWasAnswerer = myUserId === answererId;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="card max-w-md w-full">
        <h2 className={`text-2xl font-bold text-center mb-1 ${isMatch ? "text-green-600" : "text-gray-500"}`}>
          {isMatch ? "Совпадение! 🎉" : "Не совпало"}
        </h2>
        <p className="text-center text-sm text-gray-500 mb-4">{questionText}</p>

        <div className="space-y-3 mb-4">
          <div className="rounded-xl bg-primary-light/40 p-3">
            <p className="text-xs text-gray-500 mb-1">
              {iWasAnswerer ? "Ваш ответ" : "Ответ партнёра"}
            </p>
            <p className="font-medium">{answererAnswer?.text}</p>
          </div>
          <div className="rounded-xl bg-gray-100 p-3">
            <p className="text-xs text-gray-500 mb-1">
              {iWasAnswerer ? "Догадка партнёра" : "Ваша догадка"}
            </p>
            <p className="font-medium">{guesserAnswer?.text}</p>
          </div>
        </div>

        <div className="flex justify-center gap-6 text-center mb-4">
          <div>
            <p className="text-lg font-bold text-primary">+{pointsAwarded}</p>
            <p className="text-xs text-gray-500">очков</p>
          </div>
          <div>
            <p className="text-lg font-bold text-yellow-500">+{coinsAwarded}</p>
            <p className="text-xs text-gray-500">монет</p>
          </div>
        </div>

        {!ratingSubmitted ? (
          <div className="border-t pt-3">
            <p className="text-sm text-gray-500 mb-1">Оцените этот вопрос:</p>
            <RatingStars onRate={onRate} onReport={onReport} />
          </div>
        ) : (
          <p className="text-sm text-center text-gray-400 border-t pt-3">Спасибо за оценку!</p>
        )}

        <button className="btn-primary w-full mt-4" onClick={onNextRound}>
          Следующий вопрос
        </button>
      </div>
    </div>
  );
}
