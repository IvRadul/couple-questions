"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PackAdminOut, PackStatus } from "@/types";

const EXAMPLE_JSON = `{
  "name": "Название пака",
  "description": "Необязательное описание",
  "price_coins": 30,
  "questions": [
    {
      "text": "Что {username} больше всего ценит в людях?",
      "category": "быт",
      "question_type": "open"
    },
    {
      "text": "Какой формат отдыха выберет {username} в первую очередь?",
      "category": "развлечения",
      "question_type": "choice",
      "options": [
        { "text": "Вариант 1" },
        { "text": "Вариант 2" },
        { "text": "Вариант 3" }
      ]
    }
  ]
}`;

export default function AdminPage() {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [secret, setSecret] = useState("");
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claiming, setClaiming] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const me = await api.me();
        setIsAdmin(me.is_admin);
      } catch {
        setIsAdmin(false);
      }
    })();
  }, []);

  async function handleClaim(e: React.FormEvent) {
    e.preventDefault();
    setClaiming(true);
    setClaimError(null);
    try {
      const me = await api.claimAdmin(secret.trim());
      setIsAdmin(me.is_admin);
    } catch (e: any) {
      setClaimError(e.message);
    } finally {
      setClaiming(false);
    }
  }

  if (isAdmin === null) {
    return <p className="text-center text-gray-400">Загрузка...</p>;
  }

  if (!isAdmin) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-center">Админ-панель</h1>
        <div className="card space-y-3">
          <p className="text-sm text-gray-500">
            Введите секретный ключ администратора (переменная окружения{" "}
            <code className="bg-gray-100 px-1 rounded">ADMIN_SECRET_KEY</code> на бэкенде), чтобы получить
            права администратора для этого аккаунта.
          </p>
          <form onSubmit={handleClaim} className="flex flex-col gap-3">
            <input
              type="password"
              className="input"
              placeholder="Секретный ключ"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
            <button type="submit" className="btn-primary" disabled={claiming || !secret.trim()}>
              Войти как администратор
            </button>
          </form>
          {claimError && <p className="text-red-500 text-sm">{claimError}</p>}
        </div>
        <div className="text-center">
          <Link href="/game" className="text-primary underline text-sm">
            Назад к игре
          </Link>
        </div>
      </div>
    );
  }

  return <AdminDashboard />;
}

function AdminDashboard() {
  const [statusFilter, setStatusFilter] = useState<PackStatus | "all">("all");
  const [packs, setPacks] = useState<PackAdminOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [jsonText, setJsonText] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const [busyPackId, setBusyPackId] = useState<number | null>(null);

  async function loadPacks() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.adminListPacks(statusFilter === "all" ? undefined : statusFilter);
      setPacks(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPacks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setUploadError(null);
    setUploadSuccess(null);

    let payload;
    try {
      payload = JSON.parse(jsonText);
    } catch {
      setUploadError("Некорректный JSON — проверьте синтаксис");
      return;
    }

    setUploading(true);
    try {
      const pack = await api.adminUploadPack(payload);
      setUploadSuccess(`Пак «${pack.name}» загружен и сразу доступен (${pack.question_count} вопросов).`);
      setJsonText("");
      loadPacks();
    } catch (e: any) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setJsonText(String(reader.result || ""));
    reader.readAsText(file);
  }

  async function handleApprove(packId: number) {
    setBusyPackId(packId);
    try {
      await api.adminApprovePack(packId);
      loadPacks();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyPackId(null);
    }
  }

  async function handleReject(packId: number) {
    const reason = window.prompt("Причина отклонения (необязательно):") || undefined;
    setBusyPackId(packId);
    try {
      await api.adminRejectPack(packId, reason);
      loadPacks();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyPackId(null);
    }
  }

  async function handleDeactivate(packId: number) {
    if (!window.confirm("Скрыть этот пак из витрины? Уже сыгранные раунды не пострадают.")) return;
    setBusyPackId(packId);
    try {
      await api.adminDeactivatePack(packId);
      loadPacks();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyPackId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Админ-панель</h1>
        <Link href="/game" className="text-primary underline text-sm">
          Назад к игре
        </Link>
      </div>

      <div className="card space-y-3">
        <p className="font-semibold">Загрузить новый пак (JSON)</p>
        <p className="text-xs text-gray-500">
          В тексте вопроса можно использовать <code className="bg-gray-100 px-1 rounded">{"{username}"}</code> —
          при показе он заменяется именем того, кто отвечает на вопрос "про себя". Ставьте его только в
          позиции подлежащего («{"{username}"} любит...», «Что {"{username}"} ценит...») — имя вставляется
          как есть, без склонения по падежам.
        </p>
        <details className="text-xs text-gray-500">
          <summary className="cursor-pointer">Показать пример формата</summary>
          <pre className="bg-gray-100 rounded-lg p-3 mt-2 overflow-x-auto whitespace-pre-wrap">{EXAMPLE_JSON}</pre>
        </details>

        <form onSubmit={handleUpload} className="flex flex-col gap-3">
          <input type="file" accept="application/json" onChange={handleFileUpload} className="text-sm" />
          <textarea
            className="input min-h-[160px] font-mono text-xs"
            placeholder="Вставьте JSON пака сюда..."
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
          />
          <button type="submit" className="btn-primary" disabled={uploading || !jsonText.trim()}>
            Загрузить пак (сразу опубликован)
          </button>
        </form>

        {uploadError && <p className="text-red-500 text-sm">{uploadError}</p>}
        {uploadSuccess && <p className="text-green-600 text-sm">{uploadSuccess}</p>}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="font-semibold">Все паки</p>
          <select
            className="text-sm border rounded-lg px-2 py-1"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as PackStatus | "all")}
          >
            <option value="all">Все статусы</option>
            <option value="pending">На модерации</option>
            <option value="approved">Одобрены</option>
            <option value="rejected">Отклонены</option>
          </select>
        </div>

        {loading && <p className="text-center text-gray-400">Загрузка...</p>}
        {error && <p className="text-center text-red-500">{error}</p>}
        {!loading && packs.length === 0 && <p className="text-center text-gray-400">Паков нет</p>}

        {packs.map((pack) => (
          <div key={pack.id} className="card space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">
                  {pack.name}{" "}
                  <span
                    className={`text-xs font-normal ml-1 ${
                      pack.status === "approved"
                        ? "text-green-600"
                        : pack.status === "rejected"
                        ? "text-red-500"
                        : "text-yellow-600"
                    }`}
                  >
                    {pack.status === "approved" ? "одобрен" : pack.status === "rejected" ? "отклонён" : "на модерации"}
                    {!pack.is_active && " · скрыт"}
                  </span>
                </p>
                {pack.description && <p className="text-sm text-gray-500">{pack.description}</p>}
                <p className="text-xs text-gray-400 mt-1">
                  {pack.question_count} вопросов · цена {pack.price_coins} 🪙
                  {pack.is_default && " · бесплатный по умолчанию"}
                </p>
                {pack.rejection_reason && (
                  <p className="text-xs text-red-500 mt-1">Причина отклонения: {pack.rejection_reason}</p>
                )}
              </div>
              <div className="flex flex-col gap-2 shrink-0">
                {pack.status !== "approved" && (
                  <button
                    className="text-xs bg-green-500 text-white rounded-lg px-3 py-1.5 hover:bg-green-600 disabled:opacity-50"
                    onClick={() => handleApprove(pack.id)}
                    disabled={busyPackId === pack.id}
                  >
                    Одобрить
                  </button>
                )}
                {pack.status !== "rejected" && (
                  <button
                    className="text-xs bg-gray-200 text-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-300 disabled:opacity-50"
                    onClick={() => handleReject(pack.id)}
                    disabled={busyPackId === pack.id}
                  >
                    Отклонить
                  </button>
                )}
                {pack.is_active && (
                  <button
                    className="text-xs text-red-500 underline disabled:opacity-50"
                    onClick={() => handleDeactivate(pack.id)}
                    disabled={busyPackId === pack.id}
                  >
                    Скрыть
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
