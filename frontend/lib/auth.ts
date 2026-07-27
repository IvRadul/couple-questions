const TOKEN_KEY = "cq_token";
const USER_ID_KEY = "cq_user_id";
const COUPLE_ID_KEY = "cq_couple_id";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getCoupleId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(COUPLE_ID_KEY);
}

export function getUserId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(USER_ID_KEY);
}

export function saveSession(token: string, userId: string, coupleId: string | null) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_ID_KEY, userId);
  if (coupleId) {
    localStorage.setItem(COUPLE_ID_KEY, coupleId);
  } else {
    localStorage.removeItem(COUPLE_ID_KEY);
  }
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_ID_KEY);
  localStorage.removeItem(COUPLE_ID_KEY);
}

/**
 * Гарантирует, что у пользователя есть JWT. Если токена нет — регистрирует
 * нового анонимного пользователя через POST /auth/register. Пользователь
 * может позже закрепить аккаунт логином/паролем (см. /account) и в
 * будущем войти в него через /login на любом устройстве.
 */
export async function ensureAuthenticated(): Promise<string> {
  const existing = getToken();
  if (existing) return existing;

  const res = await fetch(`${API_BASE_URL}/auth/register`, { method: "POST" });
  if (!res.ok) throw new Error("Не удалось создать анонимного пользователя");
  const data = await res.json();
  saveSession(data.access_token, data.user_id, data.couple_id);
  return data.access_token;
}
