"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearSession, ensureAuthenticated } from "@/lib/auth";
import type { UserOut } from "@/types";

export default function AccountPage() {
  const router = useRouter();
  const [me, setMe] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      await ensureAuthenticated();
      try {
        const data = await api.me();
        setMe(data);
        setUsername(data.username || "");
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await api.setPassword(username.trim(), password);
      setMe(updated);
      setPassword("");
      setSuccess(
        me?.username
          ? "Логин/пароль обновлены."
          : "Готово! Теперь можно войти в этот аккаунт с другого устройства через /login."
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    const hasCredentials = !!me?.username;
    const message = hasCredentials
      ? "Выйти из аккаунта? Понадобится логин и пароль, чтобы зайти снова."
      : "У этого аккаунта не задан логин/пароль — если выйти сейчас, вернуться в него будет НЕВОЗМОЖНО, и весь прогресс (монеты, достижения) будет потерян безвозвратно. Всё равно выйти?";
    if (!window.confirm(message)) return;
    clearSession();
    router.replace("/");
  }

  if (loading) {
    return <p className="text-center text-gray-400">Загрузка...</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Аккаунт</h1>
        <Link href="/game" className="text-primary underline text-sm">
          Назад к игре
        </Link>
      </div>

      <div className="card space-y-3">
        {me?.username ? (
          <p className="text-sm text-gray-500">
            Текущий логин: <span className="font-semibold text-gray-700">{me.username}</span>. Здесь можно
            сменить логин или пароль.
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            Ваш аккаунт пока анонимный — прогресс привязан только к этому браузеру. Задайте логин и пароль,
            чтобы иметь возможность войти в него с другого устройства и не потерять прогресс, если очистите
            браузер.
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            className="input"
            placeholder="Логин"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          <input
            type="password"
            className="input"
            placeholder={me?.username ? "Новый пароль" : "Пароль"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <button type="submit" className="btn-primary" disabled={busy || !username.trim() || password.length < 6}>
            {me?.username ? "Сохранить изменения" : "Закрепить аккаунт"}
          </button>
        </form>

        {error && <p className="text-red-500 text-sm">{error}</p>}
        {success && <p className="text-green-600 text-sm">{success}</p>}
      </div>

      <div className="text-center">
        <button onClick={handleLogout} className="text-xs text-gray-400 underline hover:text-red-500">
          Выйти из аккаунта
        </button>
      </div>
    </div>
  );
}
