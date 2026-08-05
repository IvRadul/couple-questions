"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ensureAuthenticated, getToken, saveSession } from "@/lib/auth";

function WelcomePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);

  // Код приглашения (если пришли сюда за именем по пути /couple?code=... —
  // см. couple/page.tsx) нужно донести обратно до /couple, иначе он
  // потеряется и придётся вводить его руками.
  const codeFromLink = searchParams.get("code")?.replace(/\D/g, "").slice(0, 6) || "";
  const coupleTarget = codeFromLink.length === 6 ? `/couple?code=${codeFromLink}` : "/couple";

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();
      try {
        const me = await api.me();
        const token = getToken();
        if (token) {
          saveSession(token, me.id, me.couple_id);
        }
        if (me.display_name) {
          // Имя уже задано (например, прямой переход по ссылке) — сразу дальше.
          router.replace(me.couple_id ? "/game" : coupleTarget);
          return;
        }
      } catch (e: any) {
        setError(e.message);
      } finally {
        setChecking(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await api.setDisplayName(name.trim());
      router.replace(updated.couple_id ? "/game" : coupleTarget);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  if (checking) {
    return <p className="text-center text-gray-400">Загрузка...</p>;
  }

  return (
    <div className="card text-center space-y-4">
      <h1 className="text-2xl font-bold">Как вас зовут?</h1>
      <p className="text-gray-500 text-sm">
        Это имя партнёр увидит в вопросах вида «Что {name.trim() || "..."} ценит в людях больше всего?» —
        задайте его один раз, поменять можно позже на странице «Аккаунт».
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          className="input text-center"
          placeholder="Ваше имя"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={32}
          autoFocus
        />
        <button type="submit" className="btn-primary" disabled={busy || !name.trim()}>
          Продолжить
        </button>
      </form>

      {error && <p className="text-red-500 text-sm">{error}</p>}
    </div>
  );
}

export default function WelcomePage() {
  return (
    <Suspense fallback={<p className="text-center text-gray-400">Загрузка...</p>}>
      <WelcomePageContent />
    </Suspense>
  );
}
