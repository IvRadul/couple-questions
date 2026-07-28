"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PackOut } from "@/types";

const EXAMPLE_JSON = `{
  "name": "Название пака",
  "description": "Необязательное описание",
  "price_coins": 20,
  "questions": [
    { "text": "Что {username} больше всего ценит в людях?", "category": "быт", "question_type": "open" },
    {
      "text": "Какой формат отдыха выберет {username} в первую очередь?",
      "category": "развлечения",
      "question_type": "choice",
      "options": [{ "text": "Вариант 1" }, { "text": "Вариант 2" }]
    }
  ]
}`;

export default function PacksPage() {
  const [packs, setPacks] = useState<PackOut[]>([]);
  const [coins, setCoins] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyPackId, setBusyPackId] = useState<number | null>(null);

  const [showSubmitForm, setShowSubmitForm] = useState(false);
  const [submitJson, setSubmitJson] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [packsData, me] = await Promise.all([api.getPacks(), api.me()]);
      setPacks(packsData);
      setCoins(me.coins);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleUnlock(packId: number) {
    setBusyPackId(packId);
    setError(null);
    try {
      await api.unlockPack(packId);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyPackId(null);
    }
  }

  async function handleSubmitPack(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);

    let payload;
    try {
      payload = JSON.parse(submitJson);
    } catch {
      setSubmitError("Некорректный JSON — проверьте синтаксис");
      return;
    }

    setSubmitting(true);
    try {
      await api.submitPack(payload);
      setSubmitSuccess("Пак отправлен на модерацию. Он появится в списке, как только администратор его одобрит.");
      setSubmitJson("");
    } catch (e: any) {
      setSubmitError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Паки вопросов</h1>
        <Link href="/game" className="text-primary underline text-sm">
          Назад к игре
        </Link>
      </div>

      {coins !== null && (
        <p className="text-center text-sm text-gray-500">
          Ваш баланс: <span className="font-semibold text-yellow-500">🪙 {coins}</span>
        </p>
      )}

      {loading && <p className="text-center text-gray-400">Загрузка...</p>}
      {error && <p className="text-center text-red-500">{error}</p>}

      <div className="space-y-3">
        {packs.map((pack) => (
          <div key={pack.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{pack.name}</p>
                {pack.description && <p className="text-sm text-gray-500">{pack.description}</p>}
                <p className="text-xs text-gray-400 mt-1">{pack.question_count} вопросов</p>
              </div>
              {pack.unlocked ? (
                <span className="text-sm font-semibold text-green-600 whitespace-nowrap">Открыт ✓</span>
              ) : (
                <button
                  className="btn-primary whitespace-nowrap px-4 py-2 text-sm"
                  onClick={() => handleUnlock(pack.id)}
                  disabled={busyPackId === pack.id || (coins !== null && coins < pack.price_coins)}
                >
                  Открыть за 🪙{pack.price_coins}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="card space-y-3">
        <button
          className="text-sm text-primary underline"
          onClick={() => setShowSubmitForm((v) => !v)}
        >
          {showSubmitForm ? "Скрыть форму" : "Предложить свой пак вопросов"}
        </button>

        {showSubmitForm && (
          <>
            <p className="text-xs text-gray-500">
              Пак уйдёт на модерацию и появится в общем списке только после одобрения администратором.
              В тексте вопроса можно использовать <code className="bg-gray-100 px-1 rounded">{"{username}"}</code> —
              он заменится именем того, кто отвечает на вопрос "про себя" (ставьте его в начале, в роли
              подлежащего — «{"{username}"} любит...», без склонения по падежам).
            </p>
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer">Показать пример формата</summary>
              <pre className="bg-gray-100 rounded-lg p-3 mt-2 overflow-x-auto whitespace-pre-wrap">{EXAMPLE_JSON}</pre>
            </details>
            <form onSubmit={handleSubmitPack} className="flex flex-col gap-3">
              <textarea
                className="input min-h-[140px] font-mono text-xs"
                placeholder="Вставьте JSON пака сюда..."
                value={submitJson}
                onChange={(e) => setSubmitJson(e.target.value)}
              />
              <button type="submit" className="btn-primary" disabled={submitting || !submitJson.trim()}>
                Отправить на модерацию
              </button>
            </form>
            {submitError && <p className="text-red-500 text-sm">{submitError}</p>}
            {submitSuccess && <p className="text-green-600 text-sm">{submitSuccess}</p>}
          </>
        )}
      </div>

      <div className="text-center">
        <Link href="/admin" className="text-xs text-gray-400 underline hover:text-primary">
          Админ-панель
        </Link>
      </div>
    </div>
  );
}
