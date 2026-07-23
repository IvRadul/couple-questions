"use client";

interface Props {
  title: string;
  description: string;
  coinReward: number;
  onClose: () => void;
}

export default function AchievementToast({ title, description, coinReward, onClose }: Props) {
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] w-[90%] max-w-sm">
      <div className="card border-2 border-yellow-300 flex items-start gap-3">
        <div className="text-3xl">🏆</div>
        <div className="flex-1">
          <p className="font-bold">Новое достижение: {title}</p>
          <p className="text-sm text-gray-500">{description}</p>
          <p className="text-sm text-yellow-500 font-semibold">+{coinReward} монет</p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          ✕
        </button>
      </div>
    </div>
  );
}
