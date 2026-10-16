// Sample data for tests and the dev preview, after the prototype's History, Settings, and
// Security panels.
import type {
  DepthInfo,
  ProfileInfo,
  ProviderEntry,
  ProvidersReport,
  RunStatus,
  RunSummary,
  ServerSettings,
  SessionInfo,
  SlotState,
  TokenInfo,
  WritingOptions,
} from "../../api/types";

export { structure } from "./catalog";

export const writing: WritingOptions = {
  tone: "analytical",
  tone_instructions: "",
  words: 1200,
  language: "english",
  citation_marker: "numeric",
  reference_style: "APA",
  format: "report",
};

export const settings: ServerSettings = {
  writing,
  sources: "both",
  domains: { allow: [], block: [] },
  max_concurrent_runs: 2,
  questions: { clarify: true, rounds: true, timeout: 60, max_wait: 1800 },
};

/** Slots as in prototype scenario `settings`: a web run and a CLI run hold both, one waits. */
export const slots: SlotState = {
  limit: 2,
  held: [
    { run_id: "r_8b91", origin: "web", token_name: null, started: "2026-01-01T10:00:00Z" },
    { run_id: "r_8b90", origin: "cli", token_name: null, started: "2026-01-01T10:01:00Z" },
  ],
  queued: [{ run_id: "r_8b92", origin: "api", token_name: "ci-runner" }],
};

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
    { until: "select", duration_s: 108, cost: 0.003, origin: "cli" },
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
    { until: "select", duration_s: 65, cost: 0.002, origin: "api", token_name: "ci-runner" },
  ),
];

const use = (prefilter: string, score: string, llm: string) => ({
  search: "searxng",
  fetch: "firecrawl",
  prefilter,
  score,
  llm,
});

export const profiles: ProfileInfo[] = [
  {
    name: "low-vram",
    source: "user",
    active: true,
    description: "Models take turns on one small GPU; slower, fits 8 GB.",
    use: use("embeddings", "rerank", "agents"),
    model: "qwen3-14b",
    context_tokens: "auto",
    prompt_reserve_tokens: 2000,
  },
  {
    name: "workstation",
    source: "user",
    active: false,
    description: "One GPU fits all models; models stay loaded.",
    use: use("embeddings", "jev-strict", "agents"),
    model: "qwen3-14b",
    context_tokens: "auto",
    prompt_reserve_tokens: 2000,
  },
  {
    name: "nixos",
    source: "user",
    active: false,
    description: "",
    use: use("bm25", "jev-strict", "omniroute"),
    model: "qwen3-30b-a3b",
    context_tokens: "auto",
    prompt_reserve_tokens: 2000,
  },
];

const research = (
  sub: number,
  rpq: number,
  pages: number,
  ppq: number,
  rounds = 1,
  perRound = 3,
) => ({
  sub_queries: sub,
  results_per_query: rpq,
  max_pages: pages,
  passages_per_query: ppq,
  rounds,
  queries_per_round: perRound,
});

export const depths: DepthInfo[] = [
  {
    name: "quick",
    description: "Fast overview: few searches, short report.",
    values: { ...research(3, 5, 15, 6), words: 600 },
  },
  {
    name: "standard",
    description: "Balanced: today's default.",
    values: { ...research(3, 10, 40, 10), words: null },
  },
  {
    name: "deep",
    description: "Several research rounds that follow up on gaps.",
    values: { ...research(6, 10, 60, 10, 3, 3), words: 2000 },
  },
  {
    name: "exhaustive",
    description: "Many rounds and sources; slow, for thorough reports.",
    values: { ...research(10, 10, 100, 8, 5, 4), words: 3000 },
  },
];

const checked = "2026-10-03T09:00:00Z";
const entry = (block: ProviderEntry["block"], name: string, more: Partial<ProviderEntry>) => ({
  block,
  name,
  source: "user" as const,
  provider: name,
  release: "none" as const,
  ...more,
});
const builtin = (block: ProviderEntry["block"], name: string): ProviderEntry => ({
  block,
  name,
  source: "builtin",
  provider: name,
  status: "skipped",
  detail: "built in",
});

export const providers: ProvidersReport = {
  profile: "low-vram",
  gpu_policy: "exclusive",
  warnings: [],
  entries: [
    entry("search", "searxng", {
      url: "http://homelab:8888",
      device: "homelab",
      status: "degraded",
      latency_ms: 1840,
      detail: "probe over 1000 ms",
      checked_at: checked,
    }),
    entry("fetch", "firecrawl", {
      url: "http://homelab:3002",
      device: "homelab",
      status: "ok",
      latency_ms: 120,
      checked_at: checked,
    }),
    entry("prefilter", "embeddings", {
      url: "http://localhost:11434",
      model: "bge-small-en-v1.5",
      device: "desktop:gpu0",
      release: "ollama",
      status: "ok",
      latency_ms: 38,
      checked_at: checked,
    }),
    builtin("prefilter", "bm25"),
    builtin("prefilter", "none"),
    entry("score", "rerank", {
      url: "http://localhost:8081",
      model: "bge-reranker-v2-m3-Q8_0.gguf",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "unchecked",
    }),
    entry("score", "jev-strict", {
      provider: "jev",
      url: "http://localhost:8082",
      model: "qwen3-4b-jev-Q8_0.gguf",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "unchecked",
    }),
    builtin("score", "bm25"),
    entry("llm", "omniroute", {
      provider: "openai",
      url: "https://omniroute.lan/v1",
      model: "research-smart",
      device: "remote",
      status: "unchecked",
      models: [
        {
          id: "research-smart",
          context_window: 1048576,
          max_output_tokens: 32768,
          reasoning: { plan: "high", gap: "medium", write: "medium" },
        },
        {
          id: "research-fast",
          context_window: 131072,
          max_output_tokens: 16384,
          reasoning: { plan: "low", gap: "low", write: "medium" },
        },
        { id: "qwen3-30b-a3b" },
      ],
    }),
    entry("llm", "agents", {
      provider: "openai",
      url: "http://localhost:8080/v1",
      model: "qwen3-14b",
      device: "desktop:gpu0",
      release: "llama-swap",
      status: "ok",
      latency_ms: 212,
      checked_at: checked,
      models: [
        {
          id: "qwen3-14b",
          context_window: 32768,
          max_output_tokens: 8192,
          gap_context_tokens: 4000,
        },
        { id: "gemma-3-12b" },
      ],
    }),
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
