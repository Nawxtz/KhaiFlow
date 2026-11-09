import { NextRequest, NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  BackendTokens,
  REFRESH_COOKIE,
  backendUrl,
  clearSessionCookies,
  hasValidCsrf,
  jsonError,
  setSessionCookies,
} from "@/lib/server/session";

export const dynamic = "force-dynamic";

const ALLOWED_API_GROUPS = new Set(["orders", "inventory", "verification", "export"]);

function resolveBackendPath(segments: string[], search: string): string | null {
  if (segments[0] !== "api" || !ALLOWED_API_GROUPS.has(segments[1])) return null;
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    return null;
  }
  return `/${segments.map(encodeURIComponent).join("/")}${search}`;
}

async function refreshTokens(refreshToken: string): Promise<BackendTokens | null> {
  const backend = await fetch(backendUrl("/api/auth/refresh"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  return backend.ok ? ((await backend.json()) as BackendTokens) : null;
}

async function forward(request: NextRequest, context: { params: { path: string[] } }) {
  const path = resolveBackendPath(context.params.path, request.nextUrl.search);
  if (!path) return jsonError(404, "Not found");

  const readsOnly = request.method === "GET" || request.method === "HEAD";
  if (!readsOnly && !hasValidCsrf(request)) return jsonError(403, "Invalid CSRF token");

  const body = readsOnly ? undefined : await request.text();
  const callBackend = (accessToken: string) =>
    fetch(backendUrl(path), {
      method: request.method,
      headers: {
        Accept: request.headers.get("accept") || "application/json",
        "Content-Type": request.headers.get("content-type") || "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body,
      cache: "no-store",
    });

  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  let renewed: BackendTokens | null = null;
  let backend: Response | null = null;
  try {
    if (access) backend = await callBackend(access);
    if (refresh && (!backend || backend.status === 401)) {
      renewed = await refreshTokens(refresh);
      if (renewed) backend = await callBackend(renewed.access_token);
    }
  } catch {
    return jsonError(502, "Backend unavailable");
  }

  if (!backend || backend.status === 401) {
    const response = jsonError(401, "Not authenticated");
    clearSessionCookies(response);
    return response;
  }

  const headers = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = backend.headers.get(name);
    if (value) headers.set(name, value);
  }
  const response = new NextResponse(backend.status === 204 ? null : await backend.arrayBuffer(), {
    status: backend.status,
    headers,
  });
  if (renewed) setSessionCookies(response, renewed);
  return response;
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
