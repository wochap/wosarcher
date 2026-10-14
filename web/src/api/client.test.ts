import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, httpApi } from "./client";

type Call = { url: string; init: RequestInit };

function stubFetch(status: number, body: unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("httpApi", () => {
  it("turns a JSON error into ApiError with field errors", async () => {
    stubFetch(422, { error: "invalid_request", detail: "writing.words: Input should be > 0" });
    const error = await httpApi(() => {})
      .putSettings({
        sources: "both",
        writing: {} as never,
        domains: { allow: [], block: [] },
        max_concurrent_runs: 1,
      })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).fields).toEqual({ "writing.words": "Input should be > 0" });
  });

  it("calls onUnauthorized on 401", async () => {
    stubFetch(401, { error: "unauthenticated", detail: "sign in" });
    const locked = vi.fn();
    await expect(httpApi(locked).listRuns()).rejects.toBeInstanceOf(ApiError);
    expect(locked).toHaveBeenCalledOnce();
  });

  it("maps login 401 to wrong with attempts left", async () => {
    stubFetch(401, { error: "wrong_password", detail: "", attempts_left: 3 });
    const locked = vi.fn();
    expect(await httpApi(locked).login("x")).toEqual({ kind: "wrong", attemptsLeft: 3 });
    expect(locked).not.toHaveBeenCalled();
  });

  it("maps login 429 to limited with retry_after", async () => {
    stubFetch(429, { error: "rate_limited", detail: "", retry_after: 30 });
    expect(await httpApi(() => {}).login("x")).toEqual({ kind: "limited", retryAfter: 30 });
  });

  it("sends createRun as multipart", async () => {
    const calls = stubFetch(201, { run_id: "r1", status: "running" });
    const file = new File(["# notes"], "notes.md");
    await httpApi(() => {}).createRun({ query: "q" }, [file]);
    expect(calls[0].url).toBe("/api/runs");
    const form = calls[0].init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect(JSON.parse(form.get("request") as string)).toEqual({ query: "q" });
    expect((form.get("attachments") as File).name).toBe("notes.md");
  });

  it("posts rerun with no body", async () => {
    const calls = stubFetch(201, { run_id: "r2", status: "queued" });
    expect(await httpApi(() => {}).rerunRun("r1")).toEqual({ run_id: "r2", status: "queued" });
    expect(calls[0].url).toBe("/api/runs/r1/rerun");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.body).toBeUndefined();
  });

  it("resolves a cancel answered 409 run_not_active to not_active with its status", async () => {
    stubFetch(409, { error: "run_not_active", detail: "…", run_id: "r1", status: "failed" });
    expect(await httpApi(() => {}).cancelRun("r1")).toEqual({
      kind: "not_active",
      status: "failed",
    });
    stubFetch(500, { error: "internal", detail: "boom" });
    await expect(httpApi(() => {}).cancelRun("r1")).rejects.toBeInstanceOf(ApiError);
  });
  it("saves, updates, and deletes profiles and depth presets", async () => {
    const calls = stubFetch(200, {});
    const api = httpApi(() => {});
    await api.saveProfile({ name: "cloud-rerank", from: "cloud", use: { score: "rerank" } });
    await api.updateProfile("low vram", { llm: { max_output_tokens: 12288 } });
    const values = {
      sub_queries: 10,
      results_per_query: 12,
      max_pages: 200,
      passages_per_query: 8,
      rounds: 1,
      queries_per_round: 3,
      words: 1500,
    };
    await api.saveDepth({ name: "wide", values });
    await api.replaceDepth("wide", { values });
    const sent = calls.map((c) => [
      c.init.method,
      c.url,
      c.init.body && JSON.parse(c.init.body as string),
    ]);
    expect(sent).toEqual([
      ["POST", "/api/profiles", { name: "cloud-rerank", from: "cloud", use: { score: "rerank" } }],
      ["PATCH", "/api/profiles/low%20vram", { llm: { max_output_tokens: 12288 } }],
      ["POST", "/api/depths", { name: "wide", values }],
      ["PUT", "/api/depths/wide", { values }],
    ]);
    const deleted = stubFetch(204, undefined);
    await api.deleteProfile("cloud-rerank");
    await api.deleteDepth("wide");
    expect(deleted.map((c) => [c.init.method, c.url])).toEqual([
      ["DELETE", "/api/profiles/cloud-rerank"],
      ["DELETE", "/api/depths/wide"],
    ]);
  });

  it("turns a refused save into ApiError with the server's detail", async () => {
    stubFetch(409, { error: "name_taken", detail: "a depth named 'wide' already exists" });
    const values = {
      sub_queries: 1,
      results_per_query: 1,
      max_pages: 5,
      passages_per_query: 1,
      rounds: 1,
      queries_per_round: 1,
    };
    const error = await httpApi(() => {})
      .saveDepth({ name: "Wide", values })
      .catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("name_taken");
    expect((error as ApiError).message).toBe("a depth named 'wide' already exists");
  });
});
