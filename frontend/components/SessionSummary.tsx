"use client";

interface Props {
  totalRounds: number;
  matches: number;
  totalPoints: number;
  totalCoins: number;
  onDone: () => void;
}

export default function SessionSummary({ totalRounds, matches, totalPoints, totalCoins, onDone }: Props) {
  return (
    <div className="card text-center space-y-4">
      <h2 className="text-2xl font-bold">Игра завершена! 🎉</h2>
      <p className="text-gray-500">
        Совпадений: <span className="font-semibold text-primary">{matches}</span> из{" "}
        <span className="font-semibold">{totalRounds}</span>
      </p>

      <div className="flex justify-center gap-8">
        <div>
          <p className="text-2xl font-bold text-primary">+{totalPoints}</p>
          <p className="text-xs text-gray-500">очков всего</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-yellow-500">+{totalCoins}</p>
          <p className="text-xs text-gray-500">монет всего</p>
        </div>
      </div>

      <button className="btn-primary w-full" onClick={onDone}>
        Отлично!
      </button>
    </div>
  );
}
