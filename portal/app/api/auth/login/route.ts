import { NextRequest, NextResponse } from "next/server";
import { backendUrl, jsonError, setSessionCookies } from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const credentials = await request.json().catch(() => null);
  if (typeof credentials?.username !== "string" || typeof credentials?.password !== "string") {
    return jsonError(400, "Invalid request");
  }

  let backend: Response;
  try {
    backend = await fetch(backendUrl("/api/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: credentials.username, password: credentials.password }),
      cache: "no-store",
    });
  } catch {
    return jsonError(502, "Backend unavailable");
  }
  if (!backend.ok) {
    return jsonError(backend.status === 401 ? 401 : 502, "Login failed");
  }

  const body = await backend.json();
  const response = NextResponse.json({ user: body.user });
  setSessionCookies(response, body);
  return response;
}
