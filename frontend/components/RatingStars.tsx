"use client";

import { useState } from "react";

interface Props {
  onRate: (stars: number) => void;
  onReport: () => void;
  disabled?: boolean;
}

export default function RatingStars({ onRate, onReport, disabled }: Props) {
  const [selected, setSelected] = useState<number | null>(null);

  function handleClick(star: number) {
    if (disabled) return;
    setSelected(star);
    onRate(star);
  }

  return (
    <div className="flex items-center justify-between mt-4">
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => handleClick(star)}
            disabled={disabled}
            className={`text-2xl transition ${
              selected !== null && star <= selected ? "text-yellow-400" : "text-gray-300"
            } disabled:cursor-not-allowed`}
            aria-label={`Оценить на ${star} звёзд`}
          >
            ★
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onReport}
        disabled={disabled}
        className="text-sm text-gray-400 hover:text-red-500 disabled:cursor-not-allowed"
      >
        Пожаловаться
      </button>
    </div>
  );
}
