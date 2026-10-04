// The prototype's sample run (its query, sub-queries, sources, failures, files, passages,
// report, and error) as typed events and artifacts, for the run scenario fixtures.
import type { Chunk, Context, Page, Report, Score, SelectSkip, Source } from "../../api/generated";
import type { KeptPassage, RunEvent, RunSummary, WritingOptions } from "../../api/types";
import type { Screen } from "../../app/route";
import { ev, usage } from "../events";
import type { FakeData } from "../fakeApi";
import { runs, writing } from "./data";

export const QUERY =
  "How do speculative decoding methods trade off acceptance rate against draft-model size on consumer GPUs (8–12 GB)?";

export const SUB_QUERIES = [
  "speculative decoding acceptance rate vs draft model size",
  "speculative decoding consumer GPU 8GB 12GB benchmark",
  "Medusa EAGLE draft-free speculative decoding memory overhead",
  "llama.cpp --draft speculative tokens performance",
  "optimal number of speculative tokens gamma",
];

// [path, title, failure reason, author, year]
const WEB: [string, string, string, string, string][] = [
  [
    "arxiv.org/abs/2211.17192",
    "Fast Inference from Transformers via Speculative Decoding",
    "",
    "Leviathan et al.",
    "2023",
  ],
  [
    "arxiv.org/abs/2302.01318",
    "Accelerating Large Language Model Decoding with Speculative Sampling",
    "",
    "Chen et al.",
    "2023",
  ],
  [
    "arxiv.org/abs/2401.10774",
    "Medusa: Simple LLM Inference Acceleration Framework with Multiple Decoding Heads",
    "",
    "Cai et al.",
    "2024",
  ],
  [
    "arxiv.org/abs/2401.15077",
    "EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty",
    "",
    "Li et al.",
    "2024",
  ],
  [
    "huggingface.co/blog/assisted-generation",
    "Assisted Generation: a new direction toward low-latency text generation",
    "",
    "Hugging Face",
    "2023",
  ],
  ["docs.vllm.ai/en/latest/features/spec_decode.html", "Speculative Decoding — vLLM", "", "", ""],
  [
    "github.com/ggml-org/llama.cpp/pull/2926",
    "speculative : PoC for speeding-up inference via speculative sampling",
    "",
    "",
    "",
  ],
  [
    "lmsys.org/blog/2023-11-21-lookahead-decoding",
    "Break the Sequential Dependency of LLM Inference Using Lookahead Decoding",
    "",
    "Fu et al.",
    "2023",
  ],
  [
    "reddit.com/r/LocalLLaMA/comments/1c2x9qf",
    "Speculative decoding on a 3060 — is it worth it?",
    "",
    "r/LocalLLaMA",
    "2024",
  ],
  [
    "pytorch.org/blog/hitchhikers-guide-speculative-decoding",
    "A Hitchhiker’s Guide to Speculative Decoding",
    "",
    "PyTorch",
    "2024",
  ],
  ["arxiv.org/abs/2402.01528", "Decoding Speculative Decoding", "", "Yan et al.", "2024"],
  [
    "research.google/blog/looking-back-at-speculative-decoding",
    "Looking back at speculative decoding",
    "",
    "",
    "",
  ],
  [
    "developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization",
    "Mastering LLM Techniques: Inference Optimization",
    "",
    "",
    "",
  ],
  [
    "medium.com/@mlops/speculative-decoding-explained-4b1e",
    "Speculative decoding explained",
    "403 Forbidden",
    "",
    "",
  ],
  ["arxiv.org/abs/2310.07177", "Online Speculative Decoding", "", "Liu et al.", "2023"],
  [
    "news.ycombinator.com/item?id=38201544",
    "Speculative decoding in llama.cpp | Hacker News",
    "",
    "",
    "",
  ],
  [
    "docs.sglang.ai/advanced_features/speculative_decoding.html",
    "Speculative Decoding — SGLang",
    "",
    "",
    "",
  ],
  [
    "towardsdatascience.com/speculative-decoding-a-practical-guide",
    "Speculative decoding: a practical guide",
    "Timed out after 10 s",
    "",
    "",
  ],
  ["github.com/SafeAILab/EAGLE", "SafeAILab/EAGLE — official implementation", "", "", ""],
  [
    "paperswithcode.com/task/speculative-decoding",
    "Speculative Decoding | Papers With Code",
    "Disallowed by robots.txt",
    "",
    "",
  ],
  [
    "fireworks.ai/blog/speculative-decoding-production",
    "Speculative decoding in production",
    "",
    "",
    "",
  ],
  [
    "arxiv.org/abs/2404.19737",
    "Better & Faster Large Language Models via Multi-token Prediction",
    "",
    "",
    "",
  ],
];

export const FAILURES: Record<string, string> = Object.fromEntries(
  WEB.filter((w) => w[2]).map((w) => [`https://${w[0]}`, w[2]]),
);

/** Text of exactly `size` bytes (ASCII), so the file rows show the prototype's sizes. */
function fileText(title: string, size: number): string {
  const head = `# ${title}\n\n`;
  return (head + "Draft and target throughput on a 12 GB card. ".repeat(120)).slice(0, size);
}

const FILES: [string, number][] = [
  ["notes/bench-3060.md", 4403],
  ["notes/draft-models.txt", 1946],
];

export const SOURCES: Source[] = [
  ...WEB.map(([path, title, , author, published], i) => ({
    source_id: `s${String(i + 1).padStart(2, "0")}`,
    kind: "web" as const,
    uri: `https://${path}`,
    title,
    author: author || null,
    published: published || null,
  })),
  ...FILES.map(([path], i) => ({
    source_id: `f${i + 1}`,
    kind: "file" as const,
    uri: path,
    title: path.split("/").pop() ?? path,
    author: null,
    published: null,
  })),
];

export const FILE_PAGES: Page[] = FILES.map(([, size], i) => ({
  source: SOURCES[WEB.length + i],
  text: fileText(SOURCES[WEB.length + i].title, size),
}));

// [source index, heading path, display score, text]
const PASSAGES: [number, string, number, string][] = [
  [
    10,
    "4 Results › 4.2 Draft size vs. latency",
    0.94,
    "Throughput gains track draft latency more closely than draft accuracy: a draft four times smaller but ten points less accurate often wins end-to-end, because each rejected token costs only one extra target forward pass.",
  ],
  [
    0,
    "3 Analysis › 3.1 Expected walltime",
    0.91,
    "With acceptance rate α and γ drafted tokens, the expected tokens per target pass is (1 − α^(γ+1)) / (1 − α); the improvement factor shrinks as the draft’s relative cost c grows.",
  ],
  [
    22,
    "Results › Llama-3-8B Q4 + 160M draft",
    0.89,
    "On the RTX 3060 (12 GB), a 160M draft gave 1.6× tokens/s at γ=4. The 1B draft only fit with the target at Q4 and gave 1.3×, because both models contended for memory bandwidth.",
  ],
  [
    3,
    "1 Introduction",
    0.87,
    "Drafting at the feature level instead of the token level lifts acceptance to roughly 0.8 with a draft head under 1B parameters, and no separate draft model has to be loaded.",
  ],
  [
    5,
    "Speculating with a draft model",
    0.84,
    "The draft model must share the target’s tokenizer. A num_speculative_tokens value between 3 and 5 is a reasonable starting point.",
  ],
  [
    2,
    "2 Method › 2.1 Medusa heads",
    0.82,
    "Medusa adds decoding heads to the target itself, so no second model competes for VRAM; the cost is fine-tuning the heads and a tree-attention verification step.",
  ],
  [
    8,
    "Top comment",
    0.79,
    "On 8 GB cards I stopped using a separate draft — the KV cache for both models pushed me into offloading, which erased the gain. Prompt-lookup decoding was free and gave about 1.2× on code.",
  ],
  [
    4,
    "Assisted generation in practice",
    0.77,
    "Assistant models work best when the target is at least an order of magnitude larger; latency gains around 2× are typical for greedy decoding on a single GPU.",
  ],
  [
    1,
    "2 Speculative sampling",
    0.75,
    "The modified rejection-sampling scheme preserves the target distribution exactly, so the speedup comes with no change in output quality.",
  ],
  [
    23,
    "TinyLlama-1.1B",
    0.73,
    "TinyLlama as draft for Llama-2-7B: acceptance 0.61 on chat, 0.72 on code at temperature 0.",
  ],
  [
    7,
    "Why lookahead",
    0.7,
    "Lookahead decoding needs no draft model: it generates n-grams in parallel with Jacobi iterations, which helps when memory rather than compute is the constraint.",
  ],
  [
    9,
    "Tuning γ",
    0.68,
    "Speedup peaks at small γ when acceptance is low; past the peak, each extra speculated token adds verification cost that is rarely repaid.",
  ],
  [
    14,
    "1 Introduction",
    0.66,
    "Acceptance rates drop sharply under distribution shift; online distillation of the draft on live queries recovers much of the lost acceptance.",
  ],
  [
    6,
    "PR description",
    0.63,
    "--draft sets the number of tokens drafted per step. With a Q8 draft and a Q4_K_M target on consumer GPUs, gains are largest on low-entropy text such as code.",
  ],
  [
    1,
    "6 Experiments",
    0.62,
    "Across the benchmark tasks, the 4× smaller draft accepted 0.68 of tokens on average.",
  ],
  [
    10,
    "Appendix B",
    0.61,
    "Full per-task tables for every draft and target pair, with acceptance, wall-clock time, and memory use at batch size one.",
  ],
  [
    13,
    "Benchmarks",
    0.6,
    "On an RTX 4070, a 68M draft for a 7B target reached 1.9× on code completion.",
  ],
  [
    11,
    "Impact",
    0.52,
    "Speculative decoding has since been adopted across several products, where it reduced latency without changing output.",
  ],
  [
    12,
    "Batching",
    0.47,
    "In-flight batching and paged KV caches raise GPU utilization in multi-user serving.",
  ],
  [
    15,
    "Comment thread",
    0.41,
    "We got about 1.5× on a 4090 but your mileage will vary with the prompt.",
  ],
  [
    16,
    "Launch flags",
    0.36,
    "Set --speculative-algorithm EAGLE and point --speculative-draft-model-path at the draft weights.",
  ],
  [20, "Results", 0.31, "Speculative decoding cut p50 latency for code-completion traffic."],
  [
    21,
    "5 Speculative decoding",
    0.27,
    "Training with a multi-token prediction objective lets the model act as its own speculative drafter.",
  ],
  [
    18,
    "Setup",
    0.22,
    "Install with pip install -e . and download the EAGLE weights from the model hub.",
  ],
  [
    4,
    "Usage",
    0.14,
    "Assisted generation is available in transformers through the assistant_model argument.",
  ],
];

export const THRESHOLD = 0.6;
const queryOf = (k: number) => `q${(k % 5) + 1}`;
const SCORED = [20, 19, 19, 19, 19];

export const CHUNKS: Chunk[] = PASSAGES.map(([s, heading, , text], k) => ({
  chunk_id: `c${k + 1}`,
  source_id: SOURCES[s].source_id,
  heading_path: heading.split(" › "),
  position: k,
  text,
}));

/** Passages at or above the threshold that the per-query cap removed. */
const QUERY_CAPPED = new Set([16]);
const isKept = (k: number) => PASSAGES[k][2] >= THRESHOLD && !QUERY_CAPPED.has(k);

export const SCORES: Score[] = [
  ...PASSAGES.map(
    ([, , v], k): Score => ({
      chunk_id: `c${k + 1}`,
      query_id: queryOf(k),
      scorer: "rerank",
      value: v,
      display: v,
      kept: isKept(k),
      dropped: isKept(k) ? null : QUERY_CAPPED.has(k) ? "query_cap" : "threshold",
    }),
  ),
  // The first chunk scored for a second query too; its better pair in q1 is the kept one.
  {
    chunk_id: "c1",
    query_id: "q2",
    scorer: "rerank",
    value: 0.7,
    display: 0.7,
    kept: false,
    dropped: "other_query",
  },
];

function kept(k: number): KeptPassage {
  const [s, , v] = PASSAGES[k];
  const chunk = CHUNKS[k];
  return {
    chunk_id: chunk.chunk_id,
    source_id: chunk.source_id,
    title: SOURCES[s].title,
    uri: SOURCES[s].uri,
    heading_path: chunk.heading_path,
    text: chunk.text,
    display: v,
  };
}

const KEPT = PASSAGES.map((_, k) => k).filter(isKept);

/** Kept passages select did not take. */
export const SELECT_SKIPS: SelectSkip[] = [
  { chunk_id: "c15", query_id: queryOf(14), reason: "source_cap" },
  {
    chunk_id: "c16",
    query_id: queryOf(15),
    reason: "budget",
    tokens_needed: 920,
    tokens_left: 760,
  },
];
const SELECTED = KEPT.filter((k) => !SELECT_SKIPS.some((s) => s.chunk_id === `c${k + 1}`));

export const CONTEXT: Context = {
  query: QUERY,
  budget_tokens: 6000,
  used_tokens: 5240,
  passages: SELECTED.map((k) => ({
    n: k + 1,
    chunk_id: CHUNKS[k].chunk_id,
    source_id: CHUNKS[k].source_id,
    query_id: queryOf(k),
    scorer: "rerank",
    heading_path: CHUNKS[k].heading_path,
    text: CHUNKS[k].text,
    display: PASSAGES[k][2],
  })),
  sources: SOURCES.filter((s) => SELECTED.some((k) => CHUNKS[k].source_id === s.source_id)),
};

export const MD1 = `## Summary
On consumer GPUs the binding constraint for speculative decoding is usually memory, not draft accuracy. Smaller drafts tend to win end-to-end even with lower acceptance, because a rejected token costs only one extra target pass [1][2]. On 8–12 GB cards, draft-free methods are often the better trade [6][7][11].

## Acceptance rate vs. draft size
- Expected tokens per target pass rise with acceptance α, but the gain shrinks as the draft's relative cost grows [2].
- A draft four times smaller and ten points less accurate often beats a larger one [1].
- Acceptance is task-dependent: TinyLlama drafting for a 7B target reached 0.61 on chat and 0.72 on code [10], and it drops under distribution shift [13].

## What changes on a small GPU
Both models' weights and KV caches must fit. On a 12 GB RTX 3060, a 160M draft gave 1.6× while a 1B draft gave only 1.3× because of bandwidth contention [3]. Below 8 GB, users report that offloading erases the gain entirely [7].

## Recommendations
1. Start with a draft at least 10× smaller than the target that shares its tokenizer, with γ = 3–5 [5][8][12].
2. If VRAM is tight, prefer heads on the target (Medusa, EAGLE) or draft-free lookahead [4][6][11].
3. Expect the largest gains on low-entropy output such as code [14].

Output quality is unchanged in every case: verification preserves the target distribution [9].`;

export const MD2 = `## Summary
Smaller drafts usually win on consumer GPUs: memory, not draft accuracy, is the constraint [1][3].

## Key points
- A rejected token costs one extra target pass, so a cheaper draft tolerates lower acceptance [1][2].
- On a 12 GB RTX 3060, a 160M draft gave 1.6× against 1.3× for a 1B draft [3].
- Below 8 GB, a second model's KV cache forces offloading; draft-free methods avoid it [4][6][7][11].
- Start at γ = 3–5 with a tokenizer-compatible draft at least 10× smaller [5][8][12].

Quality is unchanged: verification preserves the target distribution [9].`;

export const ERR = `RuntimeError: CUDA out of memory. Tried to allocate 1.12 GiB
(GPU 0; 11.76 GiB total capacity; 10.31 GiB already allocated; 412.00 MiB free)
  at scorer.score_batch  batch 7/12, batch_size=16, max_len=512`;

const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";

/** report.json for `body`: rendered markers, cited numbers, and APA references. */
export function reportJson(body: string, marker: WritingOptions["citation_marker"]): Report {
  const cited = [...new Set([...body.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])))].sort(
    (a, b) => a - b,
  );
  const markdown = body.replace(/\[(\d+)\]/g, (whole, n: string) =>
    marker === "superscript" ? [...n].map((d) => SUP[Number(d)]).join("") : whole,
  );
  const bySource = new Map<string, number[]>();
  for (const n of cited) {
    const source = CONTEXT.passages.find((p) => p.n === n)?.source_id ?? "";
    bySource.set(source, [...(bySource.get(source) ?? []), n]);
  }
  const references = [...bySource].map(([source_id, passages]) => {
    const s = SOURCES.find((x) => x.source_id === source_id) as Source;
    const year = s.published ?? "n.d.";
    const entry = s.author
      ? `${s.author} (${year}). *${s.title}*. ${s.uri}`
      : `*${s.title}* (${year}). ${s.uri}`;
    return { source_id, passages, entry };
  });
  const refs = references.map((r) => `- ${r.entry}`).join("\n");
  return { body, markdown: `${markdown}\n\n## References\n\n${refs}\n`, cited, references };
}

const jsonl = (rows: unknown[]) => rows.map((r) => JSON.stringify(r)).join("\n");

export function artifacts(body: string, marker: WritingOptions["citation_marker"]) {
  const report = reportJson(body, marker);
  return {
    "files.jsonl": jsonl(FILE_PAGES),
    "chunks.jsonl": jsonl(CHUNKS),
    "scores.jsonl": jsonl(SCORES),
    "context.json": JSON.stringify(CONTEXT),
    "select.jsonl": jsonl(SELECT_SKIPS),
    "report.json": JSON.stringify(report),
    "report.md": report.markdown,
  };
}

/** Appends events with increasing `seq`; live-only events reuse the last one. */
export class Log {
  readonly events: RunEvent[] = [];
  seq = 0;
  constructor(readonly runId: string) {}
  add<T extends RunEvent["type"]>(
    type: T,
    data: Extract<RunEvent, { type: T }>["data"],
    stage: string | null = null,
  ) {
    const live = type === "report.delta" || type === "report.snapshot" || type === "run.queued";
    if (!live) this.seq += 1;
    this.events.push(ev(this.seq, type, data as never, stage as never, this.runId));
    return this;
  }
  done(stage: string, count: number, extra: Record<string, unknown> = {}) {
    return this.add(
      "stage.done",
      { count, seconds: 1, usage: usage(0), skipped: false, warnings: [], ...extra } as never,
      stage,
    );
  }
}

const DEVICE = "desktop:gpu0";

export function writeEvents(log: Log, body: string) {
  log.add("resource.waiting", { device: DEVICE, released_stage: "score" }, "write");
  log.add("stage.started", { device: DEVICE, provider: "llama.cpp" }, "write");
  for (let i = 0; i < body.length; i += 48) {
    log.add("report.delta", { text: body.slice(i, i + 48) }, "write");
  }
  const tokens = Math.round(body.length / 3.7);
  log.done("write", tokens, { usage: usage(6900, tokens, 0) });
  log.add("report.snapshot", { text: reportJson(body, "numeric").markdown }, "write");
  log.add("run.done", { totals: usage(46500, tokens + 160, 0), until: null } as never);
}

/** The whole sample run up to and including `run.done`. */
export function researchEvents(runId: string): RunEvent[] {
  const log = new Log(runId);
  log.add("run.started", {
    query: QUERY,
    profile: "low-vram",
    parent_run_id: null,
    until: null,
    version: 1,
  });
  log.add("stage.started", { device: DEVICE, provider: "llama.cpp" }, "plan");
  log.add(
    "plan.ready",
    { queries: SUB_QUERIES.map((text, i) => ({ id: `q${i + 1}`, text })) },
    "plan",
  );
  log.done("plan", 5, { usage: usage(1200, 160, 0) });
  log.add("stage.started", { device: null, provider: "searxng" }, "search");
  for (const [i, s] of SOURCES.slice(0, WEB.length).entries()) {
    log.add("hit.found", { url: s.uri, title: s.title, query_ids: [queryOf(i)] }, "search");
  }
  log.done("search", WEB.length);
  log.add("stage.started", { device: null, provider: "files" }, "load");
  log.done("load", FILES.length);
  log.add("stage.started", { device: null, provider: "httpx" }, "fetch");
  let fetched = 0;
  let failed = 0;
  for (const s of SOURCES.slice(0, WEB.length)) {
    const reason = FAILURES[s.uri];
    if (reason) {
      failed += 1;
      log.add("page.failed", { url: s.uri, reason }, "fetch");
    } else {
      fetched += 1;
      log.add(
        "page.fetched",
        { url: s.uri, title: s.title, source_id: s.source_id, cached: false, chars: 5200 },
        "fetch",
      );
    }
    log.add("stage.progress", { done: fetched + failed, total: WEB.length, failed }, "fetch");
  }
  log.done("fetch", fetched);
  log.add("stage.started", { device: null, provider: "markdown" }, "chunk");
  log.done("chunk", 412);
  log.add("resource.waiting", { device: DEVICE, released_stage: "plan" }, "prefilter");
  log.add("stage.started", { device: DEVICE, provider: "ollama" }, "prefilter");
  log.add("stage.progress", { done: 206, total: 412, failed: 0 }, "prefilter");
  log.add("stage.progress", { done: 412, total: 412, failed: 0 }, "prefilter");
  log.done("prefilter", 96);
  log.add("resource.waiting", { device: DEVICE, released_stage: "prefilter" }, "score");
  log.add("stage.started", { device: DEVICE, provider: "rerank" }, "score");
  let scored = 0;
  for (const [q, count] of SCORED.entries()) {
    const ks = KEPT.filter((k) => queryOf(k) === `q${q + 1}`);
    scored += count;
    log.add(
      "passages.scored",
      {
        query_id: `q${q + 1}`,
        scorer: "rerank",
        scored: count,
        kept: ks.length,
        threshold_display: THRESHOLD,
        passages: ks.map(kept),
      },
      "score",
    );
    log.add("stage.progress", { done: scored, total: 96, failed: 0 }, "score");
  }
  log.done("score", 96, { usage: usage(38400, 0, 0) });
  log.add("stage.started", { device: null, provider: "select" }, "select");
  log.done("select", SELECTED.length);
  writeEvents(log, MD1);
  return log.events;
}

/** The events before the first one that matches. */
export function upTo(events: RunEvent[], match: (e: RunEvent) => boolean): RunEvent[] {
  const i = events.findIndex(match);
  return i < 0 ? events : events.slice(0, i);
}

export const lastSeq = (events: RunEvent[]) => events.reduce((m, e) => Math.max(m, e.seq), 0);

export const RUN_ID = "r_8c21";

/** The sample run's summary: done in 2:30 unless `extra` says otherwise. */
export function summary(extra: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: RUN_ID,
    query: QUERY,
    created: "2026-10-03T14:02:00Z",
    status: "done",
    profile: "low-vram",
    sources: "both",
    version: 1,
    until: null,
    parent_run_id: null,
    fork_from: null,
    writing,
    duration_s: 150,
    cost: 0,
    ...extra,
  };
}

/** Older runs of History, after the sample run. */
export const otherRuns = runs.filter((r) => r.run_id !== RUN_ID && r.status !== "running");

/** A run scenario: the screen it opens, the fake API data, and how the preview socket plays it. */
export type Fixture = {
  screen: Screen;
  runId?: string;
  data: Partial<FakeData>;
  /** `timer` streams the events one by one; `drop` closes the socket after seq `dropAt`. */
  stream?: "timer" | "drop";
  dropAt?: number;
};

/** Events that continue `events` with the next seq numbers. */
export function followedBy(
  events: RunEvent[],
  ...next: [RunEvent["type"], unknown, string | null][]
) {
  let seq = lastSeq(events);
  const runId = events[0]?.run_id ?? RUN_ID;
  return [
    ...events,
    ...next.map(([type, data, stage]) => ev(++seq, type, data as never, stage as never, runId)),
  ];
}
