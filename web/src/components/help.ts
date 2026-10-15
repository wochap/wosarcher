// Inline help texts, verbatim from the prototype's HELP constant and keyed like it.
import {
  ArrowDown,
  Files,
  Funnel,
  Gauge,
  type Icon,
  MinusCircle,
  PencilSlash,
  Prohibit,
  Quotes,
  Stack,
  Warning,
} from "@phosphor-icons/react";

/** One row of a legend: shown instead of the body. */
export type HelpItem = { icon: Icon; term: string; text: string };
export type Help = { title: string; body: string; example?: string; items?: HelpItem[] };

export const HELP: Record<string, Help> = {
  depth: {
    title: "Depth",
    body: "How much research to do. Each preset sets the values under Advanced and a default report length. Deeper runs take longer and use more tokens.",
  },
  "d-subq": {
    title: "Sub-queries",
    body: "How many focused searches the planner writes from your question.",
  },
  "d-rpq": { title: "Results per query", body: "Search results kept for each sub-query." },
  "d-pages": {
    title: "Max pages",
    body: "Upper limit on pages fetched across all rounds. Research stops when it is reached.",
  },
  "search-language": {
    title: "Search language",
    body: "Language SearXNG searches in. Use all, auto, or a language code: two or three lowercase letters, optionally followed by a script or region, such as es, es-PE, or zh-Hans-CN. Leave empty to search every language.",
  },
  "d-qpr": {
    title: "Follow-ups per round",
    body: "Most follow-up searches the gap step writes after each round but the last. Round 1 searches the sub-queries.",
  },
  "d-rounds": {
    title: "Rounds",
    body: "Search, fetch and score passes. After each round a gap step writes the next round’s queries.",
  },
  "d-ppq": {
    title: "Passages per query",
    body: "Top-scoring passages kept for each sub-query before selection.",
  },
  q0: {
    title: "Topic line",
    body: "A short topic the planner writes from your question. Passages are ranked against it as the first query, q0. Questions up to 200 characters are searched as written; longer ones are searched by this topic.",
  },
  "w-words-def": {
    title: "Depth default",
    body: "Each depth sets a default length: Quick 600, Standard your Settings default, Deep 2,000, Exhaustive 3,000 words. Changing depth updates it until you edit it.",
  },
  kind: {
    title: "Kind",
    body: "Research answers a question: it plans searches, scores passages and writes a cited report or answer. Catalog builds a table: it crawls out from seed records, extracts one structured record per node and returns them as JSON, a table and a graph. Pick Research for “what, why, compare”; pick Catalog for “every X with its Y”.",
  },
  recipe: {
    title: "Recipe",
    body: "Report writes a cited report. Answer replies to the question directly, with citations, in at most the chosen length. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper.",
  },
  sources: {
    title: "Sources",
    body: "Web searches the internet. Files uses only your attachments. Both combines them; attachments get a share of the context budget.",
  },
  profile: {
    title: "Profile",
    body: "A saved choice of providers, model and budgets. Advanced shows its values; edits apply to this run only until you save them. Edited values show as custom.",
  },
  "p-search": { title: "Search", body: "Where sub-queries are searched." },
  "p-fetch": {
    title: "Fetch",
    body: "Downloads the pages search found and extracts their text.",
  },
  "p-prefilter": {
    title: "Prefilter",
    body: "Narrows chunks before scoring: by embedding similarity, by keyword (BM25), or not at all (passthrough).",
  },
  "p-scorer": {
    title: "Scorer",
    body: "How passages are scored. Each scorer has its own scale and candidate count.",
  },
  "p-llm": {
    title: "LLM",
    body: "The OpenAI-compatible endpoint that plans, finds gaps, and writes.",
  },
  "p-model": {
    title: "Model",
    body: "Sent to the LLM endpoint. Suggestions come from its model list. Changing the LLM resets this to that endpoint’s default model.",
  },
  "p-limits": {
    title: "Context window / Max output",
    body: "The chosen model’s limits. Set them when the model has none configured; too large a window can overflow the model.",
  },
  "p-think": {
    title: "Thinking",
    body: "How much the model reasons before answering at each step: off, low, medium or high. Higher is slower and uses more tokens.",
  },
  "p-think-draft": {
    title: "Draft thinking",
    body: "Reasoning effort for the one call that turns the brief into the structure.",
  },
  "p-think-extract": {
    title: "Extract thinking",
    body: "Reasoning effort for the extraction call made for each node. This is the call that runs hundreds of times, so keep it low unless records come back wrong.",
  },
  "p-ctx": {
    title: "Context tokens",
    body: "Token budget for the passages the writer sees. Auto fills what the model window leaves; larger values are clamped to the window.",
  },
  "p-gapctx": {
    title: "Gap context tokens",
    body: "Token budget for the passages the gap step reads between rounds.",
  },
  "p-over": {
    title: "Overridden",
    body: "This value differs from the selected profile and applies to this run only.",
  },
  recent: {
    title: "Recent & pinned",
    body: "Click a run to fill the form with its question, options and attachments. Nothing starts until you press Run research. Names and pins are kept in this browser only.",
  },
  time: {
    title: "Time per stage",
    body: "Each stage’s own working time. Waiting for the GPU (a model unloading) and time in the queue are counted separately. With several research rounds, a stage’s time is the sum of its rounds.",
  },
  attach: {
    title: "Attachments",
    body: "Markdown or text files to research alongside the web, or instead of it.",
    example: "pdf-ingest output (.md)",
  },
  "w-tone": {
    title: "Tone",
    body: "The writing style of the report. Each option in the list says what it emphasizes.",
  },
  "w-custom": {
    title: "Custom instructions",
    body: "Extra guidance added on top of the tone. Set a default here, or change it for one run.",
    example: "Focus on costs; avoid jargon.",
  },
  "w-format": {
    title: "Format",
    body: "Report writes a structured report. Answer replies to the question directly, in at most the chosen length.",
  },
  "w-words": {
    title: "Length (words)",
    body: "Target length of the report. The writer aims for it; it is not an exact count. For an answer it is the maximum.",
  },
  "w-lang": {
    title: "Language",
    body: "The language the report is written in. Sources can be in any language.",
  },
  "w-cite": {
    title: "Citation marker",
    body: "How citations look in the text.",
    example: "[1] · ¹ · (Leviathan et al., 2023)",
  },
  "w-ref": {
    title: "Reference style",
    body: "Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE.",
  },
  cont: {
    title: "Continued",
    body: "The writer reached its output limit, so it was asked to continue from where it stopped. The parts are joined into one report.",
  },
  overridden: {
    title: "Overridden",
    body: "This value differs from your default in Settings and applies to this run only.",
  },
  rwchanged: { title: "Changed", body: "This value differs from the version you are rewriting." },
  "ph-plan": { title: "Plan", body: "Splits your question into focused sub-queries for search." },
  "ph-search": {
    title: "Search",
    body: "Runs each sub-query against the search provider and collects candidate URLs.",
  },
  "ph-fetch": {
    title: "Fetch",
    body: "Downloads each URL and extracts its readable text. Failed pages are skipped and the run continues.",
  },
  "ph-load": { title: "Load", body: "Reads your attached files." },
  "ph-chunk": {
    title: "Chunk",
    body: "Splits pages and files into passages along their headings.",
  },
  "ph-prefilter": {
    title: "Prefilter",
    body: "Quickly narrows chunks with embeddings or keyword ranking before the slower scorer.",
  },
  "ph-score": { title: "Score", body: "Rates how useful each passage is for its question." },
  "ph-gap": {
    title: "Gap",
    body: "Between rounds, reads the best passages so far and writes follow-up queries for what is missing.",
  },
  rounds: {
    title: "Research rounds",
    body: "Round 1 searches the planner’s queries. Each later round searches the gap step’s follow-ups. Pages and passages are counted as new to that round.",
  },
  "r-stop": {
    title: "Why research stopped",
    body: "",
    items: [
      {
        icon: Prohibit,
        term: "no new sources",
        text: "Follow-up searches returned only pages already fetched.",
      },
      { icon: Files, term: "page limit reached", text: "Max pages was used up." },
      {
        icon: PencilSlash,
        term: "no follow-ups",
        text: "The gap step wrote no usable follow-up query, even when asked twice.",
      },
      { icon: Stack, term: "max rounds", text: "Every planned round ran." },
      {
        icon: Warning,
        term: "gap step failed",
        text: "The gap step's model call failed; the report uses the rounds that ran.",
      },
    ],
  },
  "ph-select": {
    title: "Select",
    body: "Picks the best passages that fit the writer's context budget.",
  },
  "ph-write": {
    title: "Write",
    body: "Writes the report from the selected passages and cites each claim.",
  },
  wait: {
    title: "Waiting for GPU",
    body: "Another model is unloading from the same GPU. This stage starts when it is free.",
  },
  device: {
    title: "Device",
    body: "The machine and GPU running the current stage, as labelled in the profile.",
    example: "desktop:gpu0",
  },
  scorer: {
    title: "Scorer",
    body: "Which scorer ranked the passages. “fallback” means the configured scorer failed and a simpler one took over.",
    example: "jev · rerank · bm25 · fallback",
  },
  tokens: {
    title: "Tokens and cost",
    body: "Prompt and completion tokens across all stages. Cost is $0 for local models.",
  },
  rewrite: {
    title: "Rewrite",
    body: "Writes a new version from the same passages with different writing options. No new search; it creates a linked version.",
  },
  retry: {
    title: "Retry from Score",
    body: "Reruns scoring, selection and writing on the saved pages. Useful after changing the scorer or profile.",
  },
  rerun: { title: "Rerun", body: "Starts a fresh run with the same question and attachments." },
  versions: {
    title: "Versions",
    body: "Reports that share the same research. v1 is the original; rewrites follow.",
  },
  pdevice: { title: "Device", body: "Where this provider runs, as labelled in the profile." },
  unload: {
    title: "Unload",
    body: "Whether the model can be released between phases: none, llama-swap or ollama. Exclusive GPU policy needs it.",
  },
  health: {
    title: "Health",
    body: "Not checked yet, OK, slow (degraded), down, or skipped (built in, no endpoint). Checks run only when you click Check, so idle GPU servers are never woken by opening this page.",
  },
  gpupolicy: {
    title: "GPU policy",
    body: "Shared keeps all models loaded. Exclusive unloads a model before the next one on the same GPU loads; it needs unload support.",
  },
  rdefaults: {
    title: "Run defaults",
    body: "Preselected on every new run. A profile can set its own domain lists; runs on that profile use those instead.",
  },
  "d-allow": {
    title: "Allow domains",
    body: "Only search results from these domains and their subdomains are used. Empty allows every domain. Your files are never filtered.",
    example: "gob.pe, sunat.gob.pe",
  },
  "d-block": {
    title: "Block domains",
    body: "Search results from these domains and their subdomains are dropped, even when they are also allowed.",
    example: "facebook.com",
  },
  "d-over": {
    title: "Overridden",
    body: "This list differs from the selected profile’s list and applies to this run only.",
  },
  wdefaults: {
    title: "Writing defaults",
    body: "Used for every new run. Each run can override them in its options.",
  },
  apitokens: {
    title: "API tokens",
    body: "For scripts and agents on other machines. A token is shown once, when you create it.",
  },
  "h-recipe": {
    title: "Recipe",
    body: "Report wrote a cited report; answer wrote a direct cited answer; context returned selected passages only.",
  },
  "h-version": {
    title: "Rewrite",
    body: "A new version written from an earlier run's passages. It opens next to its parent as linked versions.",
  },
  "h-cost": {
    title: "Cost",
    body: "Total for search and hosted APIs across all stages. $0 for local models.",
  },
};

const capital = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

/** The entry for `key`, including the composed `wait-<phase>` and `retry-<stage>` entries. */
export function helpFor(key: string): Help {
  if (key.startsWith("wait-")) {
    const phase = HELP[`ph-${key.slice(5)}`] ?? { title: "", body: "" };
    return { title: `${phase.title} · waiting for GPU`, body: `${HELP.wait.body} ${phase.body}` };
  }
  if (key.startsWith("retry-")) {
    const stage = key.slice(6);
    return {
      title: `Retry from ${capital(stage)}`,
      body: `Reruns ${stage} and the stages after it on the saved results of earlier stages.`,
    };
  }
  return HELP[key] ?? { title: key, body: "" };
}

/** The run's saved settings the funnel help quotes; unknown values read "–". */
export type FunnelConfig = {
  candidates?: number;
  scoreTopK?: number;
  maxPerSource?: number;
  /** The shared display threshold; null when queries differ or none is known. */
  threshold: number | null;
};

export type FunnelKey = "f-chunks" | "f-scored" | "f-kept" | "f-cited" | "legend";

/** The Passages funnel steps and the fate legend, with the run's configured values. */
export function funnelHelp(config: FunnelConfig): Record<FunnelKey, Help> {
  const value = (n: number | undefined) => (n == null ? "–" : String(n));
  const [P, K, S] = [config.candidates, config.scoreTopK, config.maxPerSource].map(value);
  const T = config.threshold == null ? "the threshold" : config.threshold.toFixed(2);
  const cited = config.maxPerSource === 1 ? "cited passage" : "cited passages";
  return {
    "f-chunks": {
      title: "Chunks",
      body: `Pages and files split along their headings. The prefilter ranks them per sub-query and passes the top ${P} of each to the scorer; the rest are “prefiltered” and never scored.`,
    },
    "f-scored": {
      title: "Scored",
      body: "Chunks the scorer rated from 0 to 1, after the prefilter.",
    },
    "f-kept": {
      title: "Kept",
      body: `Scored at least ${T} (threshold) and in the top ${K} of their sub-query (query cap).`,
    },
    "f-cited": {
      title: "Cited",
      body: `Kept passages that fit the writer’s selection: at most ${S} per source (source cap) and within the token budget. Numbered in the report.`,
    },
    legend: {
      title: "Passage fates",
      body: "",
      items: [
        {
          icon: Quotes,
          term: "cited [n]",
          text: "Selected and cited in the report. The marker follows your citation setting.",
        },
        {
          icon: Stack,
          term: "source cap",
          text: `Kept, but its source already has the maximum of ${S} ${cited}.`,
        },
        {
          icon: Gauge,
          term: "over budget",
          text: "Kept, but too long for the tokens left in the writer’s budget.",
        },
        {
          icon: Funnel,
          term: "query cap · q1",
          text: `At or above ${T}, but its sub-query already had ${K} better passages.`,
        },
        { icon: ArrowDown, term: `below ${T}`, text: "Scored under the threshold." },
        {
          icon: MinusCircle,
          term: "prefiltered",
          text: `Never scored: outside the top ${P} for every sub-query. Shown in the source view.`,
        },
      ],
    },
  };
}

// Catalog runs: the Structure panel, the catalog phases and panels, and the result's actions.
Object.assign(HELP, {
  "c-fields": {
    title: "Record fields",
    body: "The columns every record gets. A record missing a required field is dropped. ref holds another record’s id; enum takes one of the type values.",
  },
  "c-vol": { title: "Volatile", body: "Taken only from a dated source; the date is recorded" },
  "c-rel": {
    title: "Child relation",
    body: "The phrase used to find a node’s children, written in the sources’ language.",
  },
  "c-seeds": {
    title: "Seeds",
    body: "Where the crawl starts. Each seed becomes a record. When a URL is set it is fetched first instead of searched for.",
  },
  "c-leaf": {
    title: "Leaf types",
    body: "Nodes of these types are recorded but not expanded further.",
  },
  "c-expand": {
    title: "Expand by",
    body: "How children are found. Links follows links on the node’s own pages, Search queries the web for the child relation, Both does each and merges the results.",
  },
  "c-output": {
    title: "Output",
    body: "Table returns the records as JSON, a table and a graph. Report also writes a cited report from the records, with the Writing options below. Both returns the table with a Report view added.",
  },
  "c-limits": {
    title: "Limits",
    body: "Max depth counts levels below the seeds. The run stops at Max nodes. Pages per node caps fetches for each record.",
  },
  "c-lang": {
    title: "Search language",
    body: "Language used for search queries and for matching the child relation.",
  },
  "c-record-lang": {
    title: "Record language",
    body: "Language for text fields such as descriptions. Leave empty to keep the sources’ language. Names, acronyms and URLs stay as the sources give them.",
  },
  "cp-load": { title: "Load", body: "Reads the brief, the structure and any attached files." },
  "cp-draft": {
    title: "Draft",
    body: "Checks the structure and turns the seeds into starting nodes.",
  },
  "cp-expand": {
    title: "Expand",
    body: "Finds each node’s children using the child relation. Each wave expands the nodes found in the previous one; Expand through Extract repeat per wave.",
  },
  "cp-search": {
    title: "Search",
    body: "Web searches for nodes without a URL, and for the child relation when Expand by includes Search.",
  },
  "cp-fetch": { title: "Fetch", body: "Fetches up to Pages per node for each node." },
  "cp-chunk": { title: "Chunk", body: "Splits fetched pages into passages for extraction." },
  "cp-extract": {
    title: "Extract",
    body: "One extraction call per node fills its record from the passages, with a source for each value.",
  },
  "cp-assemble": {
    title: "Assemble",
    body: "Merges duplicates, resolves parent_id references and writes the table.",
  },
  "cp-write": {
    title: "Write",
    body: "Writes a cited report from the assembled records, with the run’s writing options. Runs only when Output is Report or Both.",
  },
  "c-frontier": {
    title: "Frontier",
    body: "Every node found so far, by depth. Grey dot: discovered. Pulsing ring: being expanded. Solid: extracted. Amber: failed.",
  },
  "c-coverage": {
    title: "Coverage",
    body: "How far the run is into its limits, and how often each field was filled across extracted records. The lowest fill rates are the gaps to check.",
  },
  "cr-expand": {
    title: "Expand more",
    body: "Raises max depth or max nodes and resumes from the frontier. Records already extracted are kept.",
  },
  "cr-reextract": {
    title: "Re-extract",
    body: "Runs extract and assemble again with another model. The fetched pages are kept, so nothing is crawled again.",
  },
} satisfies Record<string, Help>);
