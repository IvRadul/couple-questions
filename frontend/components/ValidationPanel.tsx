"use client";

interface Props {
  yourAnswer: string;
  guess: string;
  onValidate: (isMatch: boolean) => void;
}

export default function ValidationPanel({ yourAnswer, guess, onValidate }: Props) {
  return (
    <div className="card space-y-4">
      <p className="text-center font-medium text-gray-600">
        Партнёр попытался угадать ваш ответ. Совпадает ли догадка с тем, что вы имели в виду?
      </p>

      <div className="space-y-3">
        <div className="rounded-xl bg-primary-light/40 p-3">
          <p className="text-xs text-gray-500 mb-1">Ваш ответ</p>
          <p className="font-medium">{yourAnswer}</p>
        </div>
        <div className="rounded-xl bg-gray-100 p-3">
          <p className="text-xs text-gray-500 mb-1">Догадка партнёра</p>
          <p className="font-medium">{guess}</p>
        </div>
      </div>

      <div className="flex gap-3">
        <button
          className="flex-1 rounded-xl bg-green-500 text-white font-semibold py-3 hover:bg-green-600 transition"
          onClick={() => onValidate(true)}
        >
          Совпало ✓
        </button>
        <button
          className="flex-1 rounded-xl bg-gray-300 text-gray-700 font-semibold py-3 hover:bg-gray-400 transition"
          onClick={() => onValidate(false)}
        >
          Не совпало ✕
        </button>
      </div>
    </div>
  );
}
