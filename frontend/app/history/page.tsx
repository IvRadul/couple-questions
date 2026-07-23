"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getUserId } from "@/lib/api";
import type { HistoryItemOut } from "@/types";

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItemOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const myUserId = getUserId();

  useEffect(() => {
    (async () => {
      try {
        const data = await api.getHistory();
        setItems(data);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">История игр</h1>
        <Link href="/game" className="text-primary underline text-sm">
          Назад к игре
        </Link>
      </div>

      {loading && <p className="text-center text-gray-400">Загрузка...</p>}
      {error && <p className="text-center text-red-500">{error}</p>}
      {!loading && items.length === 0 && (
        <p className="text-center text-gray-400">Пока нет завершённых раундов</p>
      )}

      <div className="space-y-3">
        {items.map((item) => {
          const mine = item.answers.find((a) => a.user_id === myUserId);
          const partner = item.answers.find((a) => a.user_id !== myUserId);
          return (
            <div key={item.round_id} className="card">
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-semibold ${item.is_match ? "text-green-600" : "text-gray-400"}`}>
                  {item.is_match ? "Совпадение" : "Не совпало"}
                </span>
                <span className="text-xs text-gray-400">
                  {item.completed_at ? new Date(item.completed_at).toLocaleString("ru-RU") : ""}
                </span>
              </div>
              <p className="font-medium mb-2">{item.question_text}</p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-primary-light/40 p-2">
                  <p className="text-xs text-gray-500">Вы</p>
                  <p>{mine?.text}</p>
                </div>
                <div className="rounded-lg bg-gray-100 p-2">
                  <p className="text-xs text-gray-500">Партнёр</p>
                  <p>{partner?.text}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
