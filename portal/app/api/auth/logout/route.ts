import { NextRequest, NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  backendUrl,
  clearSessionCookies,
  hasValidCsrf,
  jsonError,
} from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!hasValidCsrf(request)) return jsonError(403, "Invalid CSRF token");

  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  if (access) {
    await fetch(backendUrl("/api/auth/logout"), {
      method: "POST",
      headers: { Authorization: `Bearer ${access}` },
      cache: "no-store",
    }).catch(() => undefined);
  }
  const response = new NextResponse(null, { status: 204 });
  clearSessionCookies(response);
  return response;
}
