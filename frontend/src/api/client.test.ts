import { describe, expect, it } from "vitest";
import { mockFetch } from "../test/fetchMock";
import { ApiError, api, apiGet } from "./client";

describe("apiGet", () => {
  it("returns the parsed body on success", async () => {
    mockFetch({ "/x": { body: { ok: true } } });
    await expect(apiGet("/x")).resolves.toEqual({ ok: true });
  });

  it("maps the backend error envelope to ApiError with the trace ID", async () => {
    mockFetch({
      "/x": {
        status: 404,
        headers: { "X-Request-ID": "req-123" },
        body: { error: { code: "NOT_FOUND", message: "Not Found", request_id: "req-123", details: {} } },
      },
    });
    const error = await apiGet("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "NOT_FOUND", status: 404, requestId: "req-123" });
  });

  it("reports a network failure without leaking the raw browser error", async () => {
    mockFetch({ "/x": "network-error" });
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "NETWORK_ERROR", status: null });
  });

  it("handles non-JSON error bodies", async () => {
    mockFetch({});
    globalThis.fetch = async () => new Response("<html>bad gateway</html>", { status: 502 });
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "HTTP_ERROR", status: 502 });
  });

  it("treats /ready 503 as a valid not-ready answer", async () => {
    mockFetch({
      "/api/v1/ready": {
        status: 503,
        body: { status: "not_ready", checks: { database: "unavailable", migrations: "unknown" } },
      },
    });
    await expect(api.ready()).resolves.toMatchObject({ status: "not_ready" });
  });
});

describe("admin session", () => {
  it("attaches the session token only to admin calls", async () => {
    const { session } = await import("./client");
    session.set("rws_abc.def");
    const spy = mockFetch({
      "/api/v1/health": { body: { status: "ok" } },
      "/api/v1/admin/config": { body: { policy: { version: "v" } } },
    });
    await api.health();
    await api.config();
    expect(spy.calls[0]!.auth).toBeNull();
    expect(spy.calls[1]!.auth).toBe("Bearer rws_abc.def");
  });

  it("clears the session on 401 from an admin endpoint", async () => {
    const { session } = await import("./client");
    session.set("rws_expired.x");
    mockFetch({ "/api/v1/admin/config": { status: 401, body: { error: { code: "UNAUTHORIZED", message: "no", request_id: null, details: {} } } } });
    await expect(api.config()).rejects.toMatchObject({ code: "UNAUTHORIZED" });
    expect(session.get()).toBeNull();
  });

  it("exchanges the admin token and stores only the session token", async () => {
    const { session } = await import("./client");
    const spy = mockFetch({ "POST /api/v1/admin/session": { body: { session_token: "rws_new.sig", expires_at: 1 } } });
    await api.login("the-admin-token");
    expect(spy.calls[0]!.body).toEqual({ token: "the-admin-token" });
    expect(session.get()).toBe("rws_new.sig");
    expect(JSON.stringify(sessionStorage)).not.toContain("the-admin-token");
  });
});
