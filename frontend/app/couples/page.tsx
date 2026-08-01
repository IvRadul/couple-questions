"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ensureAuthenticated, getCoupleId } from "@/lib/auth";
import { api } from "@/lib/api";
import type { CoupleHistoryItemOut } from "@/types";

export default function CouplesHistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<CoupleHistoryItemOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyCoupleId, setBusyCoupleId] = useState<string | null>(null);
  const [waitingCoupleId, setWaitingCoupleId] = useState<string | null>(null);
  const [hasCurrentCouple, setHasCurrentCouple] = useState(false);

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();
      try {
        const me = await api.me();
        if (!me.display_name) {
          router.replace("/welcome");
          return;
        }
      } catch {
        // не критично для показа списка
      }

      setHasCurrentCouple(!!getCoupleId());

      try {
        const data = await api.getCoupleHistory();
        setItems(data);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Пока ждём, чтобы партнёр тоже переподключился, опрашиваем статус пары.
  useEffect(() => {
    if (!waitingCoupleId) return;

    const interval = setInterval(async () => {
      try {
        const couple = await api.getMyCouple();
        if (couple.status === "active") {
          clearInterval(interval);
          router.replace("/game");
        }
      } catch {
        // тихо игнорируем — просто попробуем на следующем тике
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [waitingCoupleId, router]);

  async function handleReconnect(coupleId: string) {
    setBusyCoupleId(coupleId);
    setError(null);
    try {
      await api.reconnectCouple(coupleId);
      const couple = await api.getMyCouple();
      if (couple.status === "active") {
        router.replace("/game");
      } else {
        setWaitingCoupleId(coupleId);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyCoupleId(null);
    }
  }

  if (loading) {
    return <p className="text-center text-gray-400">Загрузка...</p>;
  }

  if (waitingCoupleId) {
    return (
      <div className="card text-center space-y-2">
        <p className="text-gray-500">Ждём, когда партнёр тоже переподключится...</p>
        <p className="text-sm text-gray-400">
          Как только он подтвердит — вы автоматически перейдёте в игру.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Прошлые пары</h1>
        <Link href="/couple" className="text-primary underline text-sm">
          Назад
        </Link>
      </div>

      {hasCurrentCouple && (
        <p className="text-sm text-gray-500 text-center">
          Чтобы переподключиться к другой паре, сначала выйдите из текущей (кнопка внизу экрана игры).
        </p>
      )}

      {error && <p className="text-center text-red-500 text-sm">{error}</p>}

      {items.length === 0 && <p className="text-center text-gray-400">Прошлых пар пока нет.</p>}

      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.couple_id} className="card flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">{item.partner_display_name || "Партнёр"}</p>
              {item.left_at && (
                <p className="text-xs text-gray-400">
                  Расстались {new Date(item.left_at).toLocaleDateString("ru-RU")}
                </p>
              )}
            </div>
            <button
              className="btn-primary px-4 py-2 text-sm whitespace-nowrap"
              onClick={() => handleReconnect(item.couple_id)}
              disabled={hasCurrentCouple || busyCoupleId === item.couple_id}
            >
              Переподключиться
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
