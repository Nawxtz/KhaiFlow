import { csrfHeaders } from "@/lib/csrf";

export type UserRole = "owner" | "staff";

export interface UserSession {
  id: string;
  username: string;
  role: UserRole;
}

export const STORAGE_KEY_USER = "portal_user";

export function getUser(): UserSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY_USER);
    if (!raw) return null;
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

function rememberUser(user: UserSession): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(user));
  } catch {
    // ignore
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY_USER);
  } catch {
    // ignore
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getUser());
}

export async function login(username: string, password: string): Promise<UserSession> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username.trim(), password }),
  });
  if (!response.ok) {
    throw new Error("INVALID_CREDENTIALS");
  }
  const { user } = (await response.json()) as { user: UserSession };
  rememberUser(user);
  return user;
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", headers: csrfHeaders() }).catch(() => undefined);
  clearSession();
}
