// In-memory ApiClient for tests and the dev preview. Records every call; any method can be
// replaced on the returned object to script a test.
import { type ApiClient, ApiError, type ExportFormat, type LoginResult } from "../api/client";
import type {
  DepthInfo,
  ProfileInfo,
  ProvidersReport,
  RunCreated,
  RunDetail,
  RunEvent,
  RunSummary,
  ServerSettings,
  SessionInfo,
  SlotState,
  SourceView,
  Structure,
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
  slots: SlotState;
  profiles: ProfileInfo[];
  depths: DepthInfo[];
  /** What `listModels` answers. */
  models: string[];
  providers: ProvidersReport;
  session: SessionInfo;
  tokens: TokenInfo[];
  /** What `draftStructure` answers: a structure, or an error to throw. */
  draft: Structure | ApiError | null;
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
    slots: fixtures.slots,
    profiles: fixtures.profiles,
    depths: fixtures.depths,
    models: [],
    providers: fixtures.providers,
    session: fixtures.session,
    tokens: fixtures.tokens,
    logins: [],
    draft: fixtures.structure,
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
    async draftStructure(request, attachments) {
      record("draftStructure", request, attachments);
      if (data.draft instanceof ApiError) throw data.draft;
      if (!data.draft) throw new ApiError(502, "draft_failed", "the draft call failed");
      return structuredClone(data.draft);
    },
    async rerunRun(id) {
      record("rerunRun", id);
      return created(find(id).query);
    },
    async cancelRun(id) {
      record("cancelRun", id);
      const { status } = find(id);
      if (status === "queued") return { kind: "dequeued" };
      if (status === "running" || status === "waiting") return { kind: "signalled" };
      return { kind: "not_active", status };
    },
    async continueRun(id, body) {
      record("continueRun", id, body);
      find(id);
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
    async getSlots() {
      record("getSlots");
      return structuredClone({ ...data.slots, limit: data.settings.max_concurrent_runs });
    },
    async listProfiles() {
      record("listProfiles");
      return structuredClone(data.profiles);
    },
    async saveProfile(body) {
      record("saveProfile", body);
      const base = data.profiles.find((p) => p.name === body.from);
      if (!base) throw new ApiError(404, "profile_not_found", `no profile '${body.from}'`);
      takenName("profile", body.name, data.profiles);
      const saved: ProfileInfo = {
        ...structuredClone(base),
        name: body.name,
        active: false,
        managed: false,
        description: body.description ?? base.description,
        use: { ...base.use, ...body.use },
      };
      data.profiles.push(saved);
      data.profiles.sort((a, b) => a.name.localeCompare(b.name));
      return structuredClone(saved);
    },
    async updateProfile(name, body) {
      record("updateProfile", name, body);
      const found = data.profiles.find((p) => p.name === name);
      if (!found) throw new ApiError(404, "profile_not_found", `no profile '${name}'`);
      if (found.managed) throw new ApiError(409, "managed", `profile '${name}' is managed`);
      if (body.description != null) found.description = body.description;
      found.use = { ...found.use, ...body.use };
      return structuredClone(found);
    },
    async deleteProfile(name) {
      record("deleteProfile", name);
      data.profiles = data.profiles.filter((p) => p.name !== name);
    },
    async listDepths() {
      record("listDepths");
      return structuredClone(data.depths);
    },
    async saveDepth(body) {
      record("saveDepth", body);
      takenName("depth", body.name, data.depths);
      const saved: DepthInfo = {
        name: body.name,
        description: body.description ?? "",
        source: "user",
        managed: false,
        values: { ...body.values },
      };
      data.depths.push(saved);
      return structuredClone(saved);
    },
    async replaceDepth(name, body) {
      record("replaceDepth", name, body);
      const found = data.depths.find((d) => d.name === name);
      if (!found) throw new ApiError(404, "depth_not_found", `no depth preset '${name}'`);
      found.description = body.description ?? "";
      found.values = { ...body.values };
      return structuredClone(found);
    },
    async deleteDepth(name) {
      record("deleteDepth", name);
      data.depths = data.depths.filter((d) => d.name !== name);
    },
    async listModels(llm) {
      record("listModels", llm);
      return [...data.models];
    },
    async listProviders() {
      record("listProviders");
      return structuredClone(data.providers);
    },
    async checkProviders(entries) {
      record("checkProviders", entries);
      const at = new Date().toISOString();
      for (const e of data.providers.entries) {
        const key = `${e.block}/${e.name}`;
        if (e.source !== "builtin" && (!entries?.length || entries.includes(key))) {
          if (e.status === "unchecked") e.status = "ok";
          e.checked_at = at;
        }
      }
      return structuredClone(data.providers);
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

function takenName(kind: string, name: string, existing: { name: string }[]): void {
  const taken = existing.find((e) => e.name.toLowerCase() === name.toLowerCase());
  if (taken)
    throw new ApiError(409, "name_taken", `a ${kind} named '${taken.name}' already exists`);
}

export function callsTo(api: FakeApi, method: keyof ApiClient): unknown[][] {
  return api.calls.filter((c) => c.method === method).map((c) => c.args);
}
