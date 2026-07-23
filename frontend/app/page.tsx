"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ensureAuthenticated, getCoupleId } from "@/lib/auth";

export default function HomePage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        await ensureAuthenticated();
        const coupleId = getCoupleId();
        if (coupleId) {
          router.replace("/game");
        } else {
          router.replace("/couple");
        }
      } catch (e: any) {
        setError(e.message || "Не удалось подключиться к серверу");
      }
    })();
  }, [router]);

  return (
    <div className="card text-center">
      <h1 className="text-2xl font-bold mb-2">Вопросы для пары 💞</h1>
      {error ? (
        <p className="text-red-500">{error}</p>
      ) : (
        <p className="text-gray-500">Загрузка...</p>
      )}
    </div>
  );
}
