// The question card's state for the open pause: the question shown, a draft answer for each,
// and the post of the answers. A new pause starts a fresh card.
import { useCallback, useState } from "react";
import type { ContinueRequest, Question } from "../../api/types";
import {
  answered,
  continueBody,
  type Draft,
  pickOption,
  startDrafts,
  toggleOther,
  typeOther,
} from "../../run/questions";
import type { OpenPause } from "../../run/reducer";

type Card = { pauseId: number; index: number; drafts: Draft[]; error: string };

const fresh = (pause: OpenPause): Card => ({
  pauseId: pause.pauseId,
  index: 0,
  drafts: startDrafts(pause.questions),
  error: "",
});

export type QuestionCardState = {
  pause: OpenPause;
  index: number;
  question: Question;
  draft: Draft;
  /** The current question has an answer, so Next is enabled. */
  canNext: boolean;
  last: boolean;
  /** The answers are being posted. */
  busy: boolean;
  /** The server's detail for a rejected post. */
  error: string;
  pick(optionId: string): void;
  type(text: string): void;
  toggleOther(): void;
  next(): void;
  back(): void;
  restRecommended(): void;
};

/** `post` sends the body to `POST /api/runs/{id}/continue`; null while no pause is open. */
export function useQuestionCard(
  pause: OpenPause | null,
  post: (body: ContinueRequest) => Promise<void>,
): QuestionCardState | null {
  const [state, setState] = useState<Card | null>(null);
  const [busy, setBusy] = useState(false);
  const card = pause && (state?.pauseId === pause.pauseId ? state : fresh(pause));

  const update = useCallback(
    (change: (card: Card) => Card) => {
      if (!pause) return;
      setState((held) => change(held?.pauseId === pause.pauseId ? held : fresh(pause)));
    },
    [pause],
  );

  const submit = useCallback(
    async (body: ContinueRequest) => {
      setBusy(true);
      try {
        await post(body);
        update((c) => ({ ...c, error: "" }));
      } catch (e) {
        update((c) => ({ ...c, error: (e as Error).message }));
      } finally {
        setBusy(false);
      }
    },
    [post, update],
  );

  if (!pause || !card) return null;
  const question = pause.questions[card.index];
  const draft = card.drafts[card.index];
  const last = card.index === pause.questions.length - 1;
  const edit = (change: (q: Question, d: Draft) => Draft) =>
    update((c) => ({
      ...c,
      drafts: c.drafts.map((d, i) => (i === c.index ? change(pause.questions[i], d) : d)),
    }));
  return {
    pause,
    index: card.index,
    question,
    draft,
    canNext: answered(draft),
    last,
    busy,
    error: card.error,
    pick: (id) => edit((q, d) => pickOption(q, d, id)),
    type: (text) => edit((q, d) => typeOther(q, d, text)),
    toggleOther: () => edit((q, d) => toggleOther(q, d)),
    next: () => {
      if (busy || !answered(draft)) return;
      if (!last) update((c) => ({ ...c, index: c.index + 1 }));
      else void submit(continueBody(pause, card.drafts));
    },
    back: () => update((c) => ({ ...c, index: Math.max(0, c.index - 1) })),
    restRecommended: () => {
      if (!busy) void submit(continueBody(pause, card.drafts, { index: card.index }));
    },
  };
}
