"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ensureAuthenticated, getToken, saveSession } from "@/lib/auth";
import { api } from "@/lib/api";

type Router = ReturnType<typeof useRouter>;

async function redirectAfterAuth(router: Router) {
  const me = await api.me();

  // Держим localStorage в согласии с сервером — на случай, если пара была
  // расформирована партнёром, пока эта вкладка/устройство были неактивны.
  const token = getToken();
  if (token) {
    saveSession(token, me.id, me.couple_id);
  }

  if (!me.display_name) {
    router.replace("/welcome");
    return;
  }
  router.replace(me.couple_id ? "/game" : "/couple");
}

export default function HomePage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [showChoice, setShowChoice] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    (async () => {
      // Если токен уже есть (не первый визит) — ведём дальше как обычно.
      // Если токена нет — это может быть либо правда новый человек, либо
      // тот, кто раньше закрепил аккаунт и хочет войти с этого устройства.
      // Не регистрируем анонимный аккаунт молча, а даём выбор.
      if (!getToken()) {
        setShowChoice(true);
        return;
      }
      try {
        await ensureAuthenticated();
        await redirectAfterAuth(router);
      } catch (e: any) {
        setError(e.message || "Не удалось подключиться к серверу");
      }
    })();
  }, [router]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      await ensureAuthenticated();
      await redirectAfterAuth(router);
    } catch (e: any) {
      setError(e.message || "Не удалось подключиться к серверу");
      setStarting(false);
    }
  }

  return (
    <div className="card text-center space-y-4">
      <h1 className="text-2xl font-bold">Вопросы для пары 💞</h1>

      {error && <p className="text-red-500">{error}</p>}

      {showChoice ? (
        <div className="space-y-3">
          <p className="text-gray-500">Первый раз здесь или уже закрепляли аккаунт раньше?</p>
          <button className="btn-primary w-full" onClick={handleStart} disabled={starting}>
            Начать (первый раз)
          </button>
          <Link href="/login" className="block text-primary underline text-sm">
            У меня уже есть аккаунт — войти
          </Link>
        </div>
      ) : (
        !error && <p className="text-gray-500">Загрузка...</p>
      )}
    </div>
  );
}
