// Inline help texts, verbatim from the prototype's HELP constant and keyed like it.
import {
  ArrowDown,
  Funnel,
  Gauge,
  type Icon,
  MinusCircle,
  Quotes,
  Stack,
} from "@phosphor-icons/react";

/** One row of a legend: shown instead of the body. */
export type HelpItem = { icon: Icon; term: string; text: string };
export type Help = { title: string; body: string; example?: string; items?: HelpItem[] };

export const HELP: Record<string, Help> = {
  recipe: {
    title: "Recipe",
    body: "Report writes a cited report. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper.",
  },
  sources: {
    title: "Sources",
    body: "Web searches the internet. Files uses only your attachments. Both combines them; attachments get a share of the context budget.",
  },
  profile: {
    title: "Profile",
    body: "A named set of providers (search, fetch, embeddings, scorer, LLM) and GPU behavior. The list comes from the server.",
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
  "w-words": {
    title: "Length (words)",
    body: "Target length of the report. The writer aims for it; it is not an exact count.",
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
    body: "Report wrote a cited report; context returned selected passages only.",
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
  prefilterTopK?: number;
  scoreTopK?: number;
  maxPerSource?: number;
  /** The shared display threshold; null when queries differ or none is known. */
  threshold: number | null;
};

export type FunnelKey = "f-chunks" | "f-scored" | "f-kept" | "f-cited" | "legend";

/** The Passages funnel steps and the fate legend, with the run's configured values. */
export function funnelHelp(config: FunnelConfig): Record<FunnelKey, Help> {
  const value = (n: number | undefined) => (n == null ? "–" : String(n));
  const [P, K, S] = [config.prefilterTopK, config.scoreTopK, config.maxPerSource].map(value);
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
