"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PackOut } from "@/types";

export default function PacksPage() {
  const [packs, setPacks] = useState<PackOut[]>([]);
  const [coins, setCoins] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyPackId, setBusyPackId] = useState<number | null>(null);

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
    </div>
  );
}
