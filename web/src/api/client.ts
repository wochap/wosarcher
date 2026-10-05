// Typed client for the server's /api routes. Everything goes to the page's own origin.
import type {
  DepthInfo,
  ForkCreate,
  HealthReport,
  ProfileInfo,
  RunCreate,
  RunCreated,
  RunDetail,
  RunStatus,
  RunSummary,
  ServerSettings,
  SessionInfo,
  SourceView,
  TokenCreated,
  TokenInfo,
} from "./types";

export type LoginResult =
  | { kind: "ok"; session: SessionInfo }
  | { kind: "wrong"; attemptsLeft: number }
  | { kind: "limited"; retryAfter: number };

/** What a cancel did; `not_active` is a run that had already ended (409 `run_not_active`). */
export type CancelOutcome =
  | { kind: "signalled" | "dequeued" }
  | { kind: "not_active"; status: RunStatus | null };

export interface ApiClient {
  listRuns(): Promise<RunSummary[]>;
  getRun(id: string): Promise<RunDetail>;
  createRun(request: RunCreate, attachments: File[]): Promise<RunCreated>;
  forkRun(id: string, body: ForkCreate): Promise<RunCreated>;
  rerunRun(id: string): Promise<RunCreated>;
  cancelRun(id: string): Promise<CancelOutcome>;
  deleteRun(id: string): Promise<void>;
  getArtifact(id: string, name: string): Promise<string>;
  /** A finished report or answer converted on the server (`GET /api/runs/{id}/export`). */
  exportRun(id: string, format: ExportFormat): Promise<Blob>;
  /** One source's chunks and their fates (`GET /api/runs/{id}/sources/{source_id}`). */
  source(runId: string, sourceId: string): Promise<SourceView>;
  getSettings(): Promise<ServerSettings>;
  putSettings(settings: ServerSettings): Promise<ServerSettings>;
  listProfiles(): Promise<ProfileInfo[]>;
  listDepths(): Promise<DepthInfo[]>;
  /** The stored provider checks; sends no probe. */
  health(profile?: string): Promise<HealthReport>;
  /** Probes the named blocks (every block when none) and returns the merged report. */
  checkHealth(blocks?: string[], profile?: string): Promise<HealthReport>;
  getSession(): Promise<SessionInfo>;
  login(password: string): Promise<LoginResult>;
  logout(): Promise<void>;
  listTokens(): Promise<TokenInfo[]>;
  createToken(name: string): Promise<TokenCreated>;
  deleteToken(id: string): Promise<void>;
}

/** A non-2xx answer. `fields` maps each invalid field (`writing.words`) to its message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

type Body = {
  error?: string;
  detail?: string;
  status?: RunStatus;
  attempts_left?: number;
  retry_after?: number;
};

/** `writing.words: Input should be greater than 0`, one line per field, as the server writes it. */
function fieldErrors(detail: string): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const line of detail.split("\n")) {
    const match = /^([\w.]+): (.+)$/.exec(line);
    if (match) fields[match[1]] = match[2];
  }
  return fields;
}

async function readBody(response: Response): Promise<Body> {
  try {
    return (await response.json()) as Body;
  } catch {
    return {};
  }
}

export type ExportFormat = "pdf" | "docx";

export function httpApi(onUnauthorized: () => void): ApiClient {
  async function fail(response: Response, error: Body): Promise<never> {
    const detail = error.detail ?? response.statusText;
    throw new ApiError(response.status, error.error ?? "error", detail, fieldErrors(detail));
  }

  async function send(method: string, path: string, body?: unknown): Promise<Response> {
    const init: RequestInit = { method, credentials: "same-origin" };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { "Content-Type": "application/json" };
    }
    const response = await fetch(`/api${path}`, init);
    if (response.ok) return response;
    if (response.status === 401) onUnauthorized();
    return fail(response, await readBody(response));
  }

  async function json<T>(method: string, path: string, body?: unknown): Promise<T> {
    return (await (await send(method, path, body)).json()) as T;
  }

  const run = (id: string) => `/runs/${encodeURIComponent(id)}`;
  const profileQuery = (profile?: string) =>
    profile ? `?profile=${encodeURIComponent(profile)}` : "";

  return {
    listRuns: () => json("GET", "/runs"),
    getRun: (id) => json("GET", run(id)),
    createRun: (request, attachments) => {
      const form = new FormData();
      form.append("request", JSON.stringify(request));
      for (const file of attachments) form.append("attachments", file, file.name);
      return json("POST", "/runs", form);
    },
    forkRun: (id, body) => json("POST", `${run(id)}/fork`, body),
    rerunRun: (id) => json("POST", `${run(id)}/rerun`),
    cancelRun: async (id) => {
      const response = await fetch(`/api${run(id)}/cancel`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.ok) {
        const { result } = (await response.json()) as { result: "signalled" | "dequeued" };
        return { kind: result };
      }
      if (response.status === 401) onUnauthorized();
      const error = await readBody(response);
      if (response.status === 409 && error.error === "run_not_active") {
        return { kind: "not_active", status: error.status ?? null };
      }
      return fail(response, error);
    },
    deleteRun: async (id) => void (await send("DELETE", run(id))),
    getArtifact: async (id, name) =>
      (await send("GET", `${run(id)}/artifacts/${encodeURIComponent(name)}`)).text(),
    exportRun: async (id, format) =>
      (await send("GET", `${run(id)}/export?format=${encodeURIComponent(format)}`)).blob(),
    source: (id, sourceId) => json("GET", `${run(id)}/sources/${encodeURIComponent(sourceId)}`),
    getSettings: () => json("GET", "/settings"),
    putSettings: (settings) => json("PUT", "/settings", settings),
    listProfiles: () => json("GET", "/profiles"),
    listDepths: () => json("GET", "/depths"),
    health: (profile) => json("GET", `/providers/health${profileQuery(profile)}`),
    checkHealth: (blocks, profile) =>
      json("POST", `/providers/health/check${profileQuery(profile)}`, { blocks: blocks ?? [] }),
    getSession: () => json("GET", "/session"),
    login: async (password) => {
      const response = await fetch("/api/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (response.ok) return { kind: "ok", session: (await response.json()) as SessionInfo };
      const error = await readBody(response);
      if (response.status === 401) return { kind: "wrong", attemptsLeft: error.attempts_left ?? 0 };
      if (response.status === 429) return { kind: "limited", retryAfter: error.retry_after ?? 30 };
      const detail = error.detail ?? response.statusText;
      throw new ApiError(response.status, error.error ?? "error", detail);
    },
    logout: async () => void (await send("POST", "/logout")),
    listTokens: () => json("GET", "/tokens"),
    createToken: (name) => json("POST", "/tokens", { name }),
    deleteToken: async (id) => void (await send("DELETE", `/tokens/${encodeURIComponent(id)}`)),
  };
}
