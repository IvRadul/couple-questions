import { API_BASE_URL, ensureAuthenticated, getToken, saveSession, getUserId } from "./auth";
import type {
  CoupleOut,
  QuestionOut,
  HistoryItemOut,
  AchievementOut,
  UserOut,
  PackOut,
  PackAdminOut,
  PackAdminDetailOut,
  PackUploadRequest,
} from "@/types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  await ensureAuthenticated();
  const token = getToken();

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  me: () => request<UserOut>("/users/me"),

  createCouple: async () => {
    const data = await request<{
      couple_id: string;
      invite_code: string;
      status: string;
      access_token: string;
    }>("/couples/create", { method: "POST" });
    // Сохраняем токен с couple_id сразу — иначе переход на /game
    // не сработает, пока страница не перезагрузится.
    saveSession(data.access_token, getUserId() || "", data.couple_id);
    return data;
  },

  joinCouple: async (inviteCode: string) => {
    const data = await request<{ access_token: string; user_id: string; couple_id: string }>(
      "/couples/join",
      {
        method: "POST",
        body: JSON.stringify({ invite_code: inviteCode }),
      }
    );
    saveSession(data.access_token, data.user_id, data.couple_id);
    return data;
  },

  leaveCouple: async () => {
    const data = await request<{ access_token: string; user_id: string; couple_id: string | null }>(
      "/couples/leave",
      { method: "POST" }
    );
    saveSession(data.access_token, data.user_id, data.couple_id);
    return data;
  },

  getMyCouple: () => request<CoupleOut>("/couples/me"),

  getHistory: () => request<HistoryItemOut[]>("/game/history"),

  getMyAchievements: () => request<AchievementOut[]>("/achievements/me"),

  getTopQuestions: (limit = 10) => request<QuestionOut[]>(`/questions/top?limit=${limit}`),

  rateQuestion: (payload: {
    question_id: number;
    round_id?: number;
    stars?: number;
    is_report?: boolean;
  }) =>
    request<{ status: string }>("/questions/rate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getPacks: () => request<PackOut[]>("/packs"),

  unlockPack: (packId: number) =>
    request<{ pack_id: number; remaining_coins: number }>(`/packs/${packId}/unlock`, {
      method: "POST",
    }),

  submitPack: (payload: PackUploadRequest) =>
    request<PackAdminOut>("/packs/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ---------- Admin ----------

  claimAdmin: (secret: string) =>
    request<UserOut>("/admin/claim", {
      method: "POST",
      body: JSON.stringify({ secret }),
    }),

  adminListPacks: (status?: string) =>
    request<PackAdminOut[]>(`/admin/packs${status ? `?status=${status}` : ""}`),

  adminGetPack: (packId: number) => request<PackAdminDetailOut>(`/admin/packs/${packId}`),

  adminUploadPack: (payload: PackUploadRequest) =>
    request<PackAdminOut>("/admin/packs/upload", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  adminApprovePack: (packId: number) =>
    request<PackAdminOut>(`/admin/packs/${packId}/approve`, { method: "POST" }),

  adminRejectPack: (packId: number, reason?: string) =>
    request<PackAdminOut>(`/admin/packs/${packId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || null }),
    }),

  adminDeactivatePack: (packId: number) =>
    request<{ status: string }>(`/admin/packs/${packId}`, { method: "DELETE" }),
};

export { getUserId };
