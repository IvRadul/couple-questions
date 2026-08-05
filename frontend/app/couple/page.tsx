"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ensureAuthenticated, getToken, saveSession } from "@/lib/auth";
import { api } from "@/lib/api";
import QRCodeImage from "@/components/QRCodeImage";

function CouplePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoJoining, setAutoJoining] = useState(false);
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();

      // Открыли по ссылке-приглашению (?code=123456, например из QR) — код
      // нужно достать сразу, до любых редиректов, иначе он потеряется
      // (например, если для начала нужно попасть на /welcome за именем).
      const codeFromLink = searchParams.get("code")?.replace(/\D/g, "").slice(0, 6) || "";
      if (codeFromLink.length === 6) {
        setJoinCode(codeFromLink);
      }

      let me;
      try {
        me = await api.me();
      } catch (e: any) {
        setError(e.message || "Не удалось подключиться к серверу");
        setLoading(false);
        return;
      }

      // Держим localStorage в согласии с сервером — на случай, если пара
      // была расформирована партнёром, пока эта вкладка была неактивна.
      const token = getToken();
      if (token) {
        saveSession(token, me.id, me.couple_id);
      }

      if (!me.display_name) {
        router.replace(codeFromLink.length === 6 ? `/welcome?code=${codeFromLink}` : "/welcome");
        return;
      }
      if (me.couple_id) {
        router.replace("/game");
        return;
      }

      if (codeFromLink.length === 6) {
        setAutoJoining(true);
        try {
          await api.joinCouple(codeFromLink);
          router.replace("/game");
          return;
        } catch (e: any) {
          setError(e.message);
          setAutoJoining(false);
          // не получилось — просто останется предзаполненная форма ниже,
          // можно поправить код руками и отправить ещё раз
        }
      }

      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  if (autoJoining) {
    return <p className="text-center text-gray-500">Присоединяемся к паре...</p>;
  }

  if (loading) {
    return <p className="text-center text-gray-500">Загрузка...</p>;
  }

  const joinLink = inviteCode && origin ? `${origin}/couple?code=${inviteCode}` : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-center">Создайте пару 💞</h1>

      {inviteCode ? (
        <div className="card text-center space-y-3">
          <p className="text-gray-500">Отправьте этот код партнёру:</p>
          <p className="text-4xl font-bold tracking-widest text-primary">{inviteCode}</p>

          {joinLink && (
            <>
              <div className="flex items-center gap-2 my-2">
                <div className="flex-1 h-px bg-gray-200" />
                <span className="text-xs text-gray-400">или</span>
                <div className="flex-1 h-px bg-gray-200" />
              </div>
              <QRCodeImage value={joinLink} size={180} />
              <p className="text-xs text-gray-400">
                Партнёр может отсканировать QR камерой телефона — код подставится и подключение
                произойдёт автоматически
              </p>
              <button
                type="button"
                className="text-xs text-primary underline"
                onClick={() => {
                  navigator.clipboard?.writeText(joinLink);
                }}
              >
                Скопировать ссылку
              </button>
            </>
          )}

          <p className="text-sm text-gray-400 pt-2">
            Ожидаем подключения второго участника... Как только партнёр введёт код (или перейдёт по
            ссылке/QR), вы автоматически перейдёте в игру.
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

      <div className="text-center">
        <Link href="/couples" className="text-xs text-gray-400 underline hover:text-primary">
          Прошлые пары
        </Link>
      </div>

      {error && <p className="text-red-500 text-center">{error}</p>}
    </div>
  );
}

export default function CouplePage() {
  return (
    <Suspense fallback={<p className="text-center text-gray-500">Загрузка...</p>}>
      <CouplePageContent />
    </Suspense>
  );
}
