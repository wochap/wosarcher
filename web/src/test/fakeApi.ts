// In-memory ApiClient for tests and the dev preview. Records every call; any method can be
// replaced on the returned object to script a test.
import { type ApiClient, ApiError, type ExportFormat, type LoginResult } from "../api/client";
import type {
  DepthInfo,
  HealthReport,
  ProfileInfo,
  RunCreated,
  RunDetail,
  RunEvent,
  RunSummary,
  ServerSettings,
  SessionInfo,
  SourceView,
  TokenInfo,
} from "../api/types";
import * as fixtures from "./fixtures/data";

export type FakeData = {
  /** Export answers by format: a failure `ApiError`, or bytes; default a small fixed file. */
  exports: Partial<Record<ExportFormat, ApiError | string>>;
  runs: RunSummary[];
  events: Record<string, RunEvent[]>;
  /** Artifact text by run id and name; a missing one answers 404. */
  artifacts: Record<string, Record<string, string>>;
  /** Source views by run id and source id; a missing one answers 404. */
  sources: Record<string, Record<string, SourceView>>;
  settings: ServerSettings;
  profiles: ProfileInfo[];
  depths: DepthInfo[];
  /** What `listModels` answers. */
  models: string[];
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
    exports: {},
    events: {},
    artifacts: {},
    sources: {},
    settings: fixtures.settings,
    profiles: fixtures.profiles,
    depths: fixtures.depths,
    models: [],
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
    if (!run) throw new ApiError(404, "run_not_found", `run ${id} not found`);
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
      const { status } = find(id);
      if (status === "queued") return { kind: "dequeued" };
      if (status === "running") return { kind: "signalled" };
      return { kind: "not_active", status };
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
    async exportRun(id, format) {
      record("exportRun", id, format);
      find(id);
      const answer = data.exports[format] ?? `fake ${format}`;
      if (answer instanceof ApiError) throw answer;
      return new Blob([answer]);
    },
    async source(id, sourceId) {
      record("source", id, sourceId);
      find(id);
      const view = data.sources[id]?.[sourceId];
      if (!view) throw new ApiError(404, "source_not_found", `no source ${sourceId}`);
      return structuredClone(view);
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
    async listDepths() {
      record("listDepths");
      return structuredClone(data.depths);
    },
    async listModels(profile) {
      record("listModels", profile);
      return [...data.models];
    },
    async health(profile) {
      record("health", profile);
      return structuredClone(data.health);
    },
    async checkHealth(blocks, profile) {
      record("checkHealth", blocks, profile);
      const at = new Date().toISOString();
      for (const c of data.health.checks) {
        if (c.status !== "skipped" && (!blocks?.length || blocks.includes(c.role))) {
          if (c.status === "unchecked") c.status = "ok";
          c.checked_at = at;
        }
      }
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
