import type {
  AdminConfig,
  ApiErrorBody,
  EvalRun,
  EvalRunDetail,
  HealthResponse,
  KeyCreated,
  KeyRotated,
  KeyView,
  ModelsResponse,
  Page,
  ProvidersResponse,
  ReadyResponse,
  RequestDetail,
  RequestSummary,
  TenantView,
  UsageSummary,
} from "./types";

const DEFAULT_BASE_URL = "http://localhost:8000";
const SESSION_KEY = "rw_admin_session";

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/+$/, "");

/** An error the UI can show: a stable code, a human message, and the server's trace ID. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly requestId: string | null;

  constructor(code: string, message: string, status: number | null, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

// --- admin session -----------------------------------------------------------------------
// Only the short-lived session token is kept (per browser tab). The admin token itself is sent
// once to /admin/session and never stored.

type SessionListener = (token: string | null) => void;
const listeners = new Set<SessionListener>();

export const session = {
  get(): string | null {
    try {
      return sessionStorage.getItem(SESSION_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null): void {
    try {
      if (token) sessionStorage.setItem(SESSION_KEY, token);
      else sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* storage unavailable: session lasts for this page only */
    }
    listeners.forEach((listener) => listener(token));
  },
  subscribe(listener: SessionListener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.code === "string"
  );
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  signal?: AbortSignal;
  acceptStatuses?: number[];
  auth?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = options.auth ? session.get() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("NETWORK_ERROR", "Could not reach the RouteWise API.", null, null);
  }

  const requestId = response.headers.get("X-Request-ID");
  const body: unknown = await response.json().catch(() => null);
  if (response.ok || options.acceptStatuses?.includes(response.status)) return body as T;
  if (options.auth && response.status === 401) session.set(null); // expired or revoked session
  if (isErrorBody(body)) throw new ApiError(body.error.code, body.error.message, response.status, requestId);
  throw new ApiError("HTTP_ERROR", `Request failed (${response.status}).`, response.status, requestId);
}

/** Backwards-compatible helper for public GETs. */
export function apiGet<T>(path: string, options: { signal?: AbortSignal; acceptStatuses?: number[] } = {}) {
  return apiRequest<T>(path, options);
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const admin = <T>(path: string, options: Omit<RequestOptions, "auth"> = {}) =>
  apiRequest<T>(`/api/v1/admin${path}`, { ...options, auth: true });

export interface RequestFilters {
  limit?: number;
  offset?: number;
  tenant?: string;
  status?: string;
  provider?: string;
  tier?: string;
  fallback?: boolean;
  q?: string;
  sort?: string;
}

export const api = {
  health: (signal?: AbortSignal) => apiGet<HealthResponse>("/api/v1/health", { signal }),
  // 503 is a meaningful answer from /ready ("not ready"), not a transport failure.
  ready: (signal?: AbortSignal) => apiGet<ReadyResponse>("/api/v1/ready", { signal, acceptStatuses: [503] }),
  models: (signal?: AbortSignal) => apiGet<ModelsResponse>("/api/v1/models", { signal }),
  providers: (signal?: AbortSignal) => apiGet<ProvidersResponse>("/api/v1/providers", { signal }),

  async login(adminToken: string): Promise<void> {
    const result = await apiRequest<{ session_token: string; expires_at: number }>("/api/v1/admin/session", {
      method: "POST",
      body: { token: adminToken },
    });
    session.set(result.session_token);
  },
  logout: () => session.set(null),

  usage: (params: { days?: number; bucket?: "hour" | "day"; tenant?: string }, signal?: AbortSignal) =>
    admin<UsageSummary>(`/usage${query(params)}`, { signal }),
  requests: (filters: RequestFilters, signal?: AbortSignal) =>
    admin<Page<RequestSummary>>(`/requests${query({ ...filters })}`, { signal }),
  request: (id: string, signal?: AbortSignal) => admin<RequestDetail>(`/requests/${encodeURIComponent(id)}`, { signal }),
  tenants: (signal?: AbortSignal) => admin<{ items: TenantView[] }>("/tenants", { signal }),
  createTenant: (body: Record<string, unknown>) => admin<TenantView>("/tenants", { method: "POST", body }),
  updateTenant: (slug: string, body: Record<string, unknown>) =>
    admin<TenantView>(`/tenants/${encodeURIComponent(slug)}`, { method: "PATCH", body }),
  keys: (slug: string, signal?: AbortSignal) =>
    admin<{ tenant: string; items: KeyView[] }>(`/tenants/${encodeURIComponent(slug)}/keys`, { signal }),
  createKey: (slug: string, name: string) =>
    admin<KeyCreated>(`/tenants/${encodeURIComponent(slug)}/keys`, { method: "POST", body: { name } }),
  revokeKey: (id: string) => admin<KeyView>(`/keys/${id}/revoke`, { method: "POST" }),
  rotateKey: (id: string, graceS: number) => admin<KeyRotated>(`/keys/${id}/rotate`, { method: "POST", body: { grace_s: graceS } }),
  config: (signal?: AbortSignal) => admin<AdminConfig>("/config", { signal }),
  evalRuns: (signal?: AbortSignal) => admin<{ items: EvalRun[] }>("/evaluation/runs", { signal }),
  evalRun: (id: string, signal?: AbortSignal) => admin<EvalRunDetail>(`/evaluation/runs/${id}`, { signal }),
};
