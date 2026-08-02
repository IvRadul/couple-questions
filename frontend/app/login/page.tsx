"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = await api.login(username.trim(), password);
      router.replace(data.couple_id ? "/game" : "/couple");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-center">Вход в аккаунт</h1>

      <div className="card space-y-3">
        <p className="text-sm text-gray-500">
          Введите логин и пароль, которые вы задали ранее на странице «Аккаунт». Если вы ещё не
          закрепляли аккаунт логином/паролем — просто{" "}
          <Link href="/" className="text-primary underline">
            откройте приложение
          </Link>{" "}
          заново, оно само создаст анонимный профиль.
        </p>
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
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button type="submit" className="btn-primary" disabled={busy || !username.trim() || !password}>
            Войти
          </button>
        </form>
        {error && <p className="text-red-500 text-sm">{error}</p>}
      </div>
    </div>
  );
}
