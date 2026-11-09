import { NextRequest, NextResponse } from "next/server";
import { CSRF_COOKIE, CSRF_HEADER } from "@/lib/csrf";

export const ACCESS_COOKIE = "kf_access";
export const REFRESH_COOKIE = "kf_refresh";
const REFRESH_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

export interface BackendTokens {
  access_token: string;
  refresh_token: string;
  expires_at: string;
}

export function backendUrl(path: string): string {
  return `${process.env.BACKEND_URL || "http://localhost:8000"}${path}`;
}

function cookieOptions(httpOnly: boolean) {
  return {
    httpOnly,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict" as const,
    path: "/",
  };
}

export function setSessionCookies(response: NextResponse, tokens: BackendTokens): void {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    ...cookieOptions(true),
    expires: new Date(tokens.expires_at),
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    ...cookieOptions(true),
    maxAge: REFRESH_MAX_AGE_SECONDS,
  });
  // Readable by the page on purpose: it is echoed in a header to prove same-site origin.
  response.cookies.set(CSRF_COOKIE, crypto.randomUUID(), {
    ...cookieOptions(false),
    maxAge: REFRESH_MAX_AGE_SECONDS,
  });
}

export function clearSessionCookies(response: NextResponse): void {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE]) {
    response.cookies.set(name, "", { ...cookieOptions(name !== CSRF_COOKIE), maxAge: 0 });
  }
}

export function hasValidCsrf(request: NextRequest): boolean {
  const cookie = request.cookies.get(CSRF_COOKIE)?.value;
  return Boolean(cookie) && request.headers.get(CSRF_HEADER) === cookie;
}

export function jsonError(status: number, detail: string): NextResponse {
  return NextResponse.json({ detail }, { status });
}
