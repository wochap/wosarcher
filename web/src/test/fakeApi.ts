// In-memory ApiClient for tests and the dev preview. Records every call; any method can be
// replaced on the returned object to script a test.
import { type ApiClient, ApiError, type LoginResult } from "../api/client";
import type {
  HealthReport,
  ProfileInfo,
  RunCreated,
  RunDetail,
  RunEvent,
  RunSummary,
  ServerSettings,
  SessionInfo,
  TokenInfo,
} from "../api/types";
import * as fixtures from "./fixtures/data";

export type FakeData = {
  runs: RunSummary[];
  events: Record<string, RunEvent[]>;
  /** Artifact text by run id and name; a missing one answers 404. */
  artifacts: Record<string, Record<string, string>>;
  settings: ServerSettings;
  profiles: ProfileInfo[];
  health: HealthReport;
  session: SessionInfo;
  tokens: TokenInfo[];
  /** Answers to `login`, in order; when empty, the login succeeds. */
  logins: LoginResult[];
};

export type Call = { method: keyof ApiClient; args: unknown[] };
export type FakeApi = ApiClient & { calls: Call[]; data: FakeData };

export function fakeData(overrides: Partial<FakeData> = {}): FakeData {
  return structuredClone({
    runs: fixtures.runs,
    events: {},
    artifacts: {},
    settings: fixtures.settings,
    profiles: fixtures.profiles,
    health: fixtures.health,
    session: fixtures.session,
    tokens: fixtures.tokens,
    logins: [],
    ...overrides,
  });
}

export function fakeApi(overrides: Partial<FakeData> = {}): FakeApi {
  const data = fakeData(overrides);
  const calls: Call[] = [];
  let next = 1;
  const record = (method: keyof ApiClient, ...args: unknown[]) => calls.push({ method, args });
  const find = (id: string) => {
    const run = data.runs.find((r) => r.run_id === id);
    if (!run) throw new Error(`no run ${id}`);
    return run;
  };
  const created = (query: string): RunCreated => {
    const run_id = `r_new${next++}`;
    const base = data.runs[0] ?? fixtures.runs[0];
    data.runs.unshift({ ...base, run_id, query, status: "running", parent_run_id: null });
    return { run_id, status: "running" };
  };

  const api: FakeApi = {
    calls,
    data,
    async listRuns() {
      record("listRuns");
      return structuredClone(data.runs);
    },
    async getRun(id) {
      record("getRun", id);
      const events = data.events[id] ?? [];
      const detail: RunDetail = {
        ...find(id),
        request: null,
        costs: null,
        last_seq: events.reduce((max, e) => Math.max(max, e.seq), 0),
      };
      return detail;
    },
    async createRun(request, attachments) {
      record("createRun", request, attachments);
      return created(request.query);
    },
    async forkRun(id, body) {
      record("forkRun", id, body);
      return created(find(id).query);
    },
    async rerunRun(id) {
      record("rerunRun", id);
      return created(find(id).query);
    },
    async cancelRun(id) {
      record("cancelRun", id);
    },
    async deleteRun(id) {
      record("deleteRun", id);
      data.runs = data.runs.filter((r) => r.run_id !== id);
    },
    async getArtifact(id, name) {
      record("getArtifact", id, name);
      const text = data.artifacts[id]?.[name];
      if (text === undefined) throw new ApiError(404, "not_found", `no artifact ${name}`);
      return text;
    },
    async getSettings() {
      record("getSettings");
      return structuredClone(data.settings);
    },
    async putSettings(settings) {
      record("putSettings", settings);
      data.settings = structuredClone(settings);
      return settings;
    },
    async listProfiles() {
      record("listProfiles");
      return structuredClone(data.profiles);
    },
    async health(profile) {
      record("health", profile);
      return structuredClone(data.health);
    },
    async getSession() {
      record("getSession");
      return structuredClone(data.session);
    },
    async login(password) {
      record("login", password);
      return data.logins.shift() ?? { kind: "ok", session: data.session };
    },
    async logout() {
      record("logout");
    },
    async listTokens() {
      record("listTokens");
      return structuredClone(data.tokens);
    },
    async createToken(name) {
      record("createToken", name);
      const token = `wosarcher_${"x".repeat(32)}${String(next++).padStart(4, "0")}`;
      const id = `t_new${next}`;
      data.tokens.unshift({
        id,
        name,
        masked: `wosarcher_••••${token.slice(-4)}`,
        created: new Date().toISOString(),
        last_used: null,
      });
      return { id, name, token };
    },
    async deleteToken(id) {
      record("deleteToken", id);
      data.tokens = data.tokens.filter((t) => t.id !== id);
    },
  };
  return api;
}

export function callsTo(api: FakeApi, method: keyof ApiClient): unknown[][] {
  return api.calls.filter((c) => c.method === method).map((c) => c.args);
}
