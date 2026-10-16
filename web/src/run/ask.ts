// The Questions row's choice: Ask or Don't ask, and the timeout, against the Settings defaults,
// and the `questions` of a run request.
import type { QuestionsOptions, QuestionsPatch } from "../api/types";

export const MAX_TIMEOUT = 3600;

/** The row's values kept with the New run draft; unset ones follow the settings. */
export type AskDraft = { ask?: boolean; timeout?: number | "" };

/** What the settings hold before they load. */
export const DEFAULT_QUESTIONS: QuestionsOptions = {
  clarify: true,
  rounds: true,
  timeout: 60,
  max_wait: 1800,
};

export type AskView = {
  ask: boolean;
  /** The timeout as typed. */
  timeout: number | "";
  /** The choice or the timeout differs from the settings. */
  changed: boolean;
  /** "default: ask · 60 s". */
  base: string;
};

export const defaultAsk = (q: QuestionsOptions) => q.clarify || q.rounds;

/** A typed timeout, rounded and clamped to 0 to 3600; empty stays empty. */
export function clampTimeout(text: string): number | "" {
  if (text.trim() === "" || Number.isNaN(Number(text))) return "";
  return Math.max(0, Math.min(MAX_TIMEOUT, Math.round(Number(text))));
}

export function askView(draft: AskDraft, defaults: QuestionsOptions): AskView {
  const base = defaultAsk(defaults);
  const ask = draft.ask ?? base;
  const timeout = draft.timeout ?? defaults.timeout;
  const changed = ask !== base || (timeout !== "" && timeout !== defaults.timeout);
  return {
    ask,
    timeout,
    changed,
    base: `default: ${base ? "ask" : "don’t ask"} · ${defaults.timeout} s`,
  };
}

/** `questions` of the request: both pauses follow the choice; `timeout` only when overridden. */
export function questionsPatch(draft: AskDraft, defaults: QuestionsOptions): QuestionsPatch {
  const view = askView(draft, defaults);
  const patch: QuestionsPatch = { clarify: view.ask, rounds: view.ask };
  if (view.ask && view.timeout !== "" && view.timeout !== defaults.timeout)
    patch.timeout = view.timeout;
  return patch;
}
