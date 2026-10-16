// The question card's rules: what a draft answer holds, how options and Other change it, and the
// body of `POST /api/runs/{id}/continue`. Pure, so the card only renders it.
import type { Answer, ContinueRequest, Question } from "../api/types";
import type { AnsweredPause, OpenPause, RunView } from "./reducer";

/** The answer being built for one question. */
export type Draft = { picked: string[]; other: string; otherOn: boolean };

export const multi = (q: Question) => q.kind === "multi";

/** The recommended options preselected. */
export function recommended(q: Question): Draft {
  return {
    picked: q.options.filter((o) => o.recommended).map((o) => o.id),
    other: "",
    otherOn: false,
  };
}

export const startDrafts = (questions: Question[]): Draft[] => questions.map(recommended);

/** A radio replaces the choice; a checkbox toggles one. */
export function pickOption(q: Question, draft: Draft, id: string): Draft {
  if (!multi(q)) return { ...draft, picked: [id], otherOn: false };
  const picked = draft.picked.includes(id)
    ? draft.picked.filter((p) => p !== id)
    : [...draft.picked, id];
  return { ...draft, picked };
}

/** Typing in Other selects it (in a `multi` question, while it holds text). */
export function typeOther(q: Question, draft: Draft, text: string): Draft {
  const otherOn = multi(q) ? text.trim() !== "" : true;
  return { other: text, otherOn, picked: multi(q) || !otherOn ? draft.picked : [] };
}

/** Clicking the Other row's radio or checkbox. */
export function toggleOther(q: Question, draft: Draft): Draft {
  if (!multi(q)) return { ...draft, otherOn: true, picked: [] };
  return { ...draft, otherOn: !draft.otherOn };
}

/** An option picked, or Other selected with text. */
export const answered = (draft: Draft) =>
  draft.picked.length > 0 || (draft.otherOn && draft.other.trim() !== "");

/** The draft as the API takes it: Other is sent as `other` when selected and not blank. */
export function toAnswer(q: Question, draft: Draft): Answer {
  const other = draft.otherOn ? draft.other.trim() : "";
  return {
    question_id: q.id,
    option_ids: q.options.filter((o) => draft.picked.includes(o.id)).map((o) => o.id),
    ...(other ? { other } : {}),
  };
}

/**
 * The continue body. With `rest` set, the questions after question `index` take their
 * recommended answers, and the current one too while it has none.
 */
export function continueBody(
  pause: OpenPause,
  drafts: Draft[],
  rest?: { index: number },
): ContinueRequest {
  const filled = drafts.map((draft, i) => {
    if (!rest || i < rest.index) return draft;
    if (i === rest.index && answered(draft)) return draft;
    return recommended(pause.questions[i]);
  });
  return {
    pause_id: pause.pauseId,
    answers: pause.questions.map((q, i) => toAnswer(q, filled[i])),
  };
}

/** The card's title: "Before searching", "After round 2", or "After wave 3". */
export function pauseTitle(pause: OpenPause): string {
  if (pause.kind === "clarify") return "Before searching";
  return `After ${pause.stage === "extract" ? "wave" : "round"} ${pause.after ?? 1}`;
}

/** The text a timeline card and the rounds panel show for an answered pause. */
export function answeredNote(note: AnsweredPause): string {
  if (note.answeredBy === "timeout")
    return `continued with recommended answers after ${clock(note.secondsWaited)}`;
  return `${note.count} answers`;
}

/** Seconds as m:ss, rounded up. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** A line under a timeline card or a round: `warn` when the run went on by timeout. */
export type AskNote = { text: string; warn: boolean };

/** What the timeline and the rounds panel show about the run's questions. */
export type AskState = {
  /** The card that waits for the user and how many questions precede the current one. */
  waiting: { stage: string; answered: number; total: number } | null;
  /** Answered pauses by card; the last one wins. */
  stages: Record<string, AskNote>;
  /** Answered pauses by research round: a clarify pause counts for round 1. */
  rounds: Record<number, AskNote>;
};

/** From the events alone: the open pause, the answered ones, and `index` for "<i> of <N> answered". */
export function askState(run: RunView, index: number): AskState {
  const stages: Record<string, AskNote> = {};
  const rounds: Record<number, AskNote> = {};
  for (const note of run.answered) {
    const line = { text: answeredNote(note), warn: note.answeredBy === "timeout" };
    stages[note.stage] = line;
    rounds[note.kind === "clarify" ? 1 : (note.after ?? 1)] = line;
  }
  const pause = run.pause;
  const waiting = pause
    ? { stage: pause.stage, answered: index, total: pause.questions.length }
    : null;
  return { waiting, stages, rounds };
}
