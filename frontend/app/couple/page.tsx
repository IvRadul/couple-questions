"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ensureAuthenticated, getCoupleId } from "@/lib/auth";
import { api } from "@/lib/api";

export default function CouplePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();
      if (getCoupleId()) {
        router.replace("/game");
        return;
      }
      setLoading(false);
    })();
  }, [router]);

  async function handleCreate() {
    if (busy || inviteCode) return; // защита от повторного клика/повторного вызова
    setBusy(true);
    setError(null);
    try {
      const data = await api.createCouple();
      setInviteCode(data.invite_code);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // Пока показан код приглашения, опрашиваем сервер: как только партнёр
  // присоединится (couple.status === "active"), уходим на экран игры.
  useEffect(() => {
    if (!inviteCode) return;

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
  }, [inviteCode, router]);

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.joinCouple(joinCode.trim());
      router.replace("/game");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-center text-gray-500">Загрузка...</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-center">Создайте пару 💞</h1>

      {inviteCode ? (
        <div className="card text-center space-y-3">
          <p className="text-gray-500">Отправьте этот код партнёру:</p>
          <p className="text-4xl font-bold tracking-widest text-primary">{inviteCode}</p>
          <p className="text-sm text-gray-400">
            Ожидаем подключения второго участника... Как только партнёр введёт код, вы автоматически
            перейдёте в игру.
          </p>
        </div>
      ) : (
        <div className="card space-y-3">
          <p className="font-medium">Ещё нет пары?</p>
          <button className="btn-primary w-full" onClick={handleCreate} disabled={busy}>
            Создать код приглашения
          </button>
        </div>
      )}

      <div className="card space-y-3">
        <p className="font-medium">Уже есть код от партнёра?</p>
        <form onSubmit={handleJoin} className="flex flex-col gap-3">
          <input
            className="input tracking-widest text-center text-xl"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="000000"
            maxLength={6}
          />
          <button type="submit" className="btn-primary" disabled={busy || joinCode.length !== 6}>
            Присоединиться
          </button>
        </form>
      </div>

      {error && <p className="text-red-500 text-center">{error}</p>}
    </div>
  );
}
