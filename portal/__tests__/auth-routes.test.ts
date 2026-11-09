// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { GET as proxyGet, POST as proxyPost } from "@/app/api/backend/[...path]/route";

const tokens = {
  access_token: "access-1",
  refresh_token: "refresh-1",
  expires_at: "2099-01-01T00:00:00Z",
  user: { id: 1, username: "owner_a", role: "owner" },
};
const fetchMock = vi.fn();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function req(url: string, init: { method?: string; body?: string; cookie?: string; csrf?: string }) {
  const headers = new Headers();
  if (init.cookie) headers.set("cookie", init.cookie);
  if (init.csrf) headers.set("X-CSRF-Token", init.csrf);
  return new NextRequest(`http://portal.test${url}`, {
    method: init.method ?? "GET",
    body: init.body,
    headers,
  });
}

const ctx = (...path: string[]) => ({ params: { path } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("login route", () => {
  it("keeps tokens out of the response body and in httpOnly cookies", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, tokens));

    const res = await login(
      req("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: "owner_a", password: "a long passphrase" }),
      })
    );

    const text = await res.text();
    expect(text).not.toContain("access-1");
    expect(text).not.toContain("refresh-1");
    expect(JSON.parse(text).user.username).toBe("owner_a");
    expect(res.cookies.get("kf_access")).toMatchObject({ value: "access-1", httpOnly: true, sameSite: "strict" });
    expect(res.cookies.get("kf_refresh")).toMatchObject({ value: "refresh-1", httpOnly: true });
    expect(res.cookies.get("kf_csrf")?.httpOnly).toBeFalsy();
  });

  it("returns 401 and sets no cookie for wrong credentials", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid credentials" }));

    const res = await login(
      req("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: "owner_a", password: "wrong password" }),
      })
    );

    expect(res.status).toBe(401);
    expect(res.cookies.get("kf_access")).toBeUndefined();
  });

  it("rejects a malformed body without calling the backend", async () => {
    const res = await login(req("/api/auth/login", { method: "POST", body: "not json" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("backend proxy", () => {
  it("sends the session cookie to the backend as a bearer token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));

    const res = await proxyGet(
      req("/api/backend/api/orders?status=ALL", { cookie: "kf_access=access-1" }),
      ctx("api", "orders")
    );

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/orders?status=ALL");
    expect(init.headers.Authorization).toBe("Bearer access-1");
  });

  it("refuses a write without the CSRF header", async () => {
    const res = await proxyPost(
      req("/api/backend/api/verification/approve/ORD-1", {
        method: "POST",
        body: "{}",
        cookie: "kf_access=access-1; kf_csrf=abc",
      }),
      ctx("api", "verification", "approve", "ORD-1")
    );

    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows a write when the CSRF header matches the cookie", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { status: "approved" }));

    const res = await proxyPost(
      req("/api/backend/api/verification/approve/ORD-1", {
        method: "POST",
        body: "{}",
        cookie: "kf_access=access-1; kf_csrf=abc",
        csrf: "abc",
      }),
      ctx("api", "verification", "approve", "ORD-1")
    );

    expect(res.status).toBe(200);
  });

  it.each([
    [["api", "auth", "login"]],
    [["api", "pdpa", "delete"]],
    [["other", "orders"]],
    [["api", "orders", "..", "pdpa"]],
  ])("does not forward path %j", async (path) => {
    const res = await proxyGet(req("/api/backend/x", { cookie: "kf_access=access-1" }), ctx(...path));

    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refreshes once after an expired access token and stores the new tokens", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { ...tokens, access_token: "access-2", refresh_token: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse(200, []));

    const res = await proxyGet(
      req("/api/backend/api/orders", { cookie: "kf_access=old; kf_refresh=refresh-1" }),
      ctx("api", "orders")
    );

    expect(res.status).toBe(200);
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer access-2");
    expect(res.cookies.get("kf_access")?.value).toBe("access-2");
  });

  it("clears cookies when the session cannot be renewed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, {})).mockResolvedValueOnce(jsonResponse(401, {}));

    const res = await proxyGet(
      req("/api/backend/api/orders", { cookie: "kf_access=old; kf_refresh=dead" }),
      ctx("api", "orders")
    );

    expect(res.status).toBe(401);
    expect(res.cookies.get("kf_access")?.value).toBe("");
  });

  it("returns 401 without calling the backend when there is no session", async () => {
    const res = await proxyGet(req("/api/backend/api/orders", {}), ctx("api", "orders"));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("logout route", () => {
  it("needs the CSRF header", async () => {
    const res = await logout(req("/api/auth/logout", { method: "POST", cookie: "kf_csrf=abc" }));

    expect(res.status).toBe(403);
  });

  it("revokes the backend session and clears cookies", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    const res = await logout(
      req("/api/auth/logout", { method: "POST", cookie: "kf_access=access-1; kf_csrf=abc", csrf: "abc" })
    );

    expect(res.status).toBe(204);
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/auth/logout");
    expect(res.cookies.get("kf_access")?.value).toBe("");
  });
});
