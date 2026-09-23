export type UserRole = "owner" | "staff";

export interface UserSession {
  id: string;
  username: string;
  role: UserRole;
}

export const STORAGE_KEY_TOKEN = "portal_session_token";
export const STORAGE_KEY_USER = "portal_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(STORAGE_KEY_TOKEN);
  } catch {
    return null;
  }
}

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

export function setSession(token: string, user: UserSession): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY_TOKEN, token);
    localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(user));
  } catch {
    // ignore
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    localStorage.removeItem(STORAGE_KEY_USER);
  } catch {
    // ignore
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

export async function login(
  username: string,
  password: string
): Promise<{ token: string; user: UserSession }> {
  // Simulate network latency
  await new Promise((resolve) => setTimeout(resolve, 50));

  const trimmedUsername = username.trim().toLowerCase();
  if (
    (trimmedUsername === "owner" && password === "password") ||
    (trimmedUsername === "staff" && password === "password")
  ) {
    const role: UserRole = trimmedUsername === "owner" ? "owner" : "staff";
    const user: UserSession = {
      id: `seller_${trimmedUsername}`,
      username: trimmedUsername,
      role,
    };
    const token = `mock_session_token_${Date.now()}_${trimmedUsername}`;
    setSession(token, user);
    return { token, user };
  }

  throw new Error("INVALID_CREDENTIALS");
}
