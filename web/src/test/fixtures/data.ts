// Sample data for tests and the dev preview, after the prototype's History, Settings, and
// Security panels.
import type {
  DepthInfo,
  HealthReport,
  ProfileInfo,
  RunStatus,
  RunSummary,
  ServerSettings,
  SessionInfo,
  TokenInfo,
  WritingOptions,
} from "../../api/types";

export const writing: WritingOptions = {
  tone: "analytical",
  tone_instructions: "",
  words: 1200,
  language: "english",
  citation_marker: "numeric",
  reference_style: "APA",
};

export const settings: ServerSettings = { writing, sources: "both" };

function run(
  run_id: string,
  query: string,
  created: string,
  status: RunStatus,
  extra: Partial<RunSummary> = {},
): RunSummary {
  return {
    run_id,
    query,
    created,
    status,
    profile: "low-vram",
    sources: "both",
    version: 1,
    until: null,
    writing,
    duration_s: status === "running" || status === "queued" ? null : 192,
    cost: status === "running" || status === "queued" ? null : 0.006,
    ...extra,
  };
}

export const runs: RunSummary[] = [
  run(
    "r_8c21",
    "How do speculative decoding methods trade off acceptance rate against draft-model size on consumer GPUs (8–12 GB)?",
    "2026-10-03T14:02:00Z",
    "running",
  ),
  run(
    "r_7f41",
    "Compare pgvector HNSW vs IVFFlat recall and build time at 1M rows",
    "2026-10-02T21:31:00Z",
    "done",
    {
      parent_run_id: "r_7f3a",
      version: 2,
      fork_from: "write",
      writing: { ...writing, tone: "explanatory", words: 300 },
      duration_s: 48,
      cost: 0,
    },
  ),
  run(
    "r_7f3a",
    "Compare pgvector HNSW vs IVFFlat recall and build time at 1M rows",
    "2026-10-02T21:14:00Z",
    "done",
  ),
  run(
    "r_7e90",
    "What changed in the Python 3.13 free-threaded build for C extensions?",
    "2026-10-02T16:40:00Z",
    "done",
    { until: "select", duration_s: 108, cost: 0.003 },
  ),
  run(
    "r_7e2c",
    "llama.cpp KV cache quantization quality impact, q8_0 vs q4_0",
    "2026-10-01T23:02:00Z",
    "failed",
    { duration_s: 41, cost: 0.001 },
  ),
  run(
    "r_7d11",
    "Rust async cancellation safety patterns with tokio::select!",
    "2026-10-01T10:15:00Z",
    "done",
    { duration_s: 245, cost: 0.008 },
  ),
  run(
    "r_7b77",
    "Is SQLite WAL mode safe on network filesystems?",
    "2026-09-29T14:11:00Z",
    "cancelled",
    { duration_s: 37, cost: 0.002 },
  ),
  run(
    "r_79d0",
    "Embedding models under 500M params ranked on MTEB retrieval",
    "2026-09-25T18:20:00Z",
    "interrupted",
    { until: "select", duration_s: 65, cost: 0.002 },
  ),
];

export const profiles: ProfileInfo[] = [
  {
    name: "low-vram",
    source: "builtin",
    active: true,
    description: "Models take turns on one small GPU; slower, fits 8 GB.",
    context_window: 32768,
    prompt_reserve_tokens: 2000,
    max_output_tokens: null,
  },
  {
    name: "workstation",
    source: "builtin",
    active: false,
    description: "One GPU fits all models; models stay loaded.",
    context_window: 32768,
    prompt_reserve_tokens: 2000,
    max_output_tokens: null,
  },
  {
    name: "cloud",
    source: "builtin",
    active: false,
    description: "Hosted APIs only; needs API keys.",
    context_window: 1000000,
    prompt_reserve_tokens: 2000,
    max_output_tokens: 32000,
  },
  { name: "nixos", source: "user", active: false, description: "" },
];

const research = (sub: number, rpq: number, pages: number, ppq: number, ctx: number) => ({
  sub_queries: sub,
  results_per_query: rpq,
  max_pages: pages,
  passages_per_query: ppq,
  context_tokens: ctx,
});

export const depths: DepthInfo[] = [
  {
    name: "quick",
    description: "Fast overview: few searches, short report.",
    values: { ...research(2, 5, 15, 6, 8000), words: 600 },
  },
  {
    name: "standard",
    description: "Balanced: today's default.",
    values: { ...research(3, 10, 40, 10, 16000), words: null },
  },
  {
    name: "deep",
    description: "More searches and sources, longer report.",
    values: { ...research(5, 10, 60, 10, 24000), words: 2000 },
  },
  {
    name: "exhaustive",
    description: "Many searches and sources; slow, for thorough reports.",
    values: { ...research(8, 10, 100, 8, 32000), words: 3000 },
  },
];

export const health: HealthReport = {
  profile: "low-vram",
  gpu_policy: "exclusive",
  warnings: [],
  checks: [
    {
      role: "search",
      provider: "searxng",
      url: "http://localhost:8888",
      model: null,
      device: null,
      release: "none",
      status: "degraded",
      latency_ms: 1840,
      detail: "probe over 1000 ms",
      checked_at: "2026-10-03T09:00:00Z",
    },
    {
      role: "fetch",
      provider: "httpx",
      url: "in-process",
      model: null,
      device: null,
      release: "none",
      status: "skipped",
      latency_ms: null,
      detail: "built in",
      checked_at: null,
    },
    {
      role: "prefilter",
      provider: "embeddings",
      url: "http://localhost:11434",
      model: "bge-small-en-v1.5",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "ok",
      latency_ms: 38,
      detail: "",
      checked_at: "2026-10-03T09:00:00Z",
    },
    {
      role: "score",
      provider: "rerank",
      url: "http://localhost:8081",
      model: "bge-reranker-v2-m3-Q8_0.gguf",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "unchecked",
      latency_ms: null,
      detail: "",
      checked_at: null,
    },
    {
      role: "llm",
      provider: "llama.cpp",
      url: "http://localhost:8080/v1",
      model: "qwen2.5-7b-instruct-q4_k_m.gguf",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "ok",
      latency_ms: 212,
      detail: "",
      checked_at: "2026-10-03T09:00:00Z",
    },
  ],
};

export const session: SessionInfo = {
  method: "cookie",
  since: "2026-10-03T09:12:00Z",
  expires: "2026-11-02T09:12:00Z",
  token_name: null,
};

export const tokens: TokenInfo[] = [
  {
    id: "t1",
    name: "cli · laptop",
    masked: "wosarcher_••••k9Qz",
    created: "2026-09-12T10:00:00Z",
    last_used: "2026-10-03T12:00:00Z",
  },
  {
    id: "t2",
    name: "ci-runner",
    masked: "wosarcher_••••2fWb",
    created: "2026-08-30T10:00:00Z",
    last_used: "2026-10-02T08:00:00Z",
  },
  {
    id: "t3",
    name: "obsidian-plugin",
    masked: "wosarcher_••••Lm07",
    created: "2026-07-04T10:00:00Z",
    last_used: null,
  },
];
