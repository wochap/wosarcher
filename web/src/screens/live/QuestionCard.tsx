// The question card of a waiting run (scenarios `live-clarify`, `live-clarify-idle`,
// `live-round-input`): one question at a time with its options, Other, and the timeout chip.
import { ArrowLeft, ArrowRight, Pause, PencilSimple, Play, Timer } from "@phosphor-icons/react";
import { type ReactNode, useEffect, useRef } from "react";
import { HelpTip } from "../../components/HelpTip";
import { usePresence } from "../../run/presence";
import { clock, multi, pauseTitle } from "../../run/questions";
import css from "./QuestionCard.module.css";
import type { QuestionCardState } from "./useQuestionCard";

type Props = {
  card: QuestionCardState;
  /** Sends the presence message on the run's event socket. */
  onPresence: () => void;
};

const DIALOGS = 'dialog, [role="dialog"], [role="alertdialog"]';

/** The timeout chip: "waiting for you" while active, else a countdown from the full timeout. */
function TimeoutChip({ left }: { left: number | null }) {
  const idle = left !== null;
  const text = idle ? clock(left) : "waiting for you";
  const Glyph = idle ? Timer : Pause;
  return (
    <HelpTip
      help="qtimeout"
      ariaLabel={
        idle
          ? `Continues with recommended answers in ${text}. Help: Timeout`
          : "Waiting for you. Help: Timeout"
      }
      className={css.chip}
    >
      <Glyph aria-hidden="true" />
      <span>{text}</span>
    </HelpTip>
  );
}

/** The options' group, named by the question: radios in a radiogroup, checkboxes in a group. */
function Options({ multi: many, children }: { multi: boolean; children: ReactNode }) {
  return many ? (
    // biome-ignore lint/a11y/useSemanticElements: a labelled group of checkboxes
    <div role="group" aria-labelledby="qa-q" className={css.options}>
      {children}
    </div>
  ) : (
    <div role="radiogroup" aria-labelledby="qa-q" className={css.options}>
      {children}
    </div>
  );
}

export function QuestionCard({ card, onPresence }: Props) {
  const { pause, question, draft, index } = card;
  const total = pause.questions.length;
  const isMulti = multi(question);
  const mono = pause.kind === "round" && isMulti;
  const left = usePresence(true, pause.timeout, onPresence);
  const other = useRef<HTMLInputElement>(null);
  const latest = useRef(card);
  latest.current = card;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (e.altKey || e.ctrlKey || e.metaKey || target?.closest(DIALOGS)) return;
      const current = latest.current;
      const tag = target?.tagName ?? "";
      const box = tag === "INPUT" && /^(radio|checkbox)$/.test((target as HTMLInputElement).type);
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag) && !box;
      if (e.key === "Enter" && (!typing || target?.dataset.qaOther) && tag !== "BUTTON") {
        e.preventDefault();
        current.next();
      } else if ((!typing || box) && /^[1-9]$/.test(e.key)) {
        const n = Number(e.key) - 1;
        const options = current.question.options;
        if (n < options.length) {
          e.preventDefault();
          current.pick(options[n].id);
        } else if (current.question.allow_other && n === options.length) {
          e.preventDefault();
          if (!current.draft.otherOn) current.toggleOther();
          other.current?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const group = `qa-opt-${pause.pauseId}-${index}`;
  const type = isMulti ? "checkbox" : "radio";
  const pct =
    left === null || !pause.timeout ? 0 : Math.max(0, Math.min(100, (left / pause.timeout) * 100));
  const keys = (n: number) => (n < 9 ? String(n + 1) : "");
  return (
    <section aria-label="Run questions" className={css.card}>
      <header className={css.header}>
        <h2 className={css.title}>{pauseTitle(pause)}</h2>
        <span role="img" aria-label={`Question ${index + 1} of ${total}`} className={css.step}>
          {index + 1} / {total}
          <span aria-hidden="true" className={css.dots}>
            {pause.questions.map((q, i) => (
              <span
                key={q.id}
                className={css.dot}
                data-state={i < index ? "done" : i === index ? "current" : "todo"}
              />
            ))}
          </span>
        </span>
        {pause.timeout > 0 && <TimeoutChip left={left} />}
      </header>
      <div aria-hidden="true" className={css.track} data-idle={left !== null}>
        <div className={css.fill} style={{ width: `${pct}%` }} />
      </div>
      <div className={css.body}>
        {pause.context && <p className={css.context}>{pause.context}</p>}
        <div id="qa-q" className={css.question}>
          {question.text}
        </div>
        <Options multi={isMulti}>
          {question.options.map((option, i) => {
            const on = draft.picked.includes(option.id);
            return (
              <label key={option.id} className={css.option} data-on={on}>
                <input
                  type={type}
                  name={group}
                  className={css.input}
                  checked={on}
                  onChange={() => card.pick(option.id)}
                />
                <span className={css.text}>
                  <span className={css.labelLine}>
                    <span className={mono ? `${css.label} ${css.mono}` : css.label}>
                      {option.label}
                    </span>
                    {option.recommended && <span className={css.recommended}>recommended</span>}
                  </span>
                  {option.description && (
                    <span className={css.description}>{option.description}</span>
                  )}
                </span>
                <kbd className={`${css.key} ${css.hint}`}>{keys(i)}</kbd>
              </label>
            );
          })}
          {question.allow_other && (
            // biome-ignore lint/a11y/noStaticElementInteractions: a click anywhere on the row focuses its input
            // biome-ignore lint/a11y/useKeyWithClickEvents: the keyboard reaches the row's inputs directly
            <div
              className={css.other}
              data-on={draft.otherOn}
              onClick={(e) => {
                const el = e.target as HTMLElement;
                if (el === other.current || el.tagName === "INPUT") return;
                other.current?.focus();
                if (!draft.otherOn) card.toggleOther();
              }}
            >
              <input
                type={type}
                name={group}
                className={css.input}
                checked={draft.otherOn}
                aria-label="Other"
                onChange={card.toggleOther}
              />
              <span className={css.otherLabel}>
                <PencilSimple aria-hidden="true" />
                Other
              </span>
              <input
                ref={other}
                data-qa-other="1"
                className={mono ? `input ${css.otherInput} ${css.mono}` : `input ${css.otherInput}`}
                value={draft.other}
                placeholder={mono ? "Add a query" : "Write your own answer"}
                aria-label="Other: your own answer"
                autoComplete="off"
                onChange={(e) => card.type(e.target.value)}
              />
              <kbd className={`${css.key} ${css.hint}`}>{keys(question.options.length)}</kbd>
            </div>
          )}
        </Options>
      </div>
      <div className={css.footer}>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={index === 0 || card.busy}
          onClick={card.back}
        >
          <ArrowLeft aria-hidden="true" />
          Back
        </button>
        <span className={css.spacer} />
        <button
          type="button"
          className="btn btn-ghost"
          disabled={card.busy}
          onClick={card.restRecommended}
        >
          Use recommended for the rest
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!card.canNext || card.busy}
          onClick={card.next}
        >
          {card.last ? "Continue" : "Next"}
          {card.last ? <Play aria-hidden="true" /> : <ArrowRight aria-hidden="true" />}
        </button>
      </div>
      {card.error && (
        <div role="alert" className={css.error}>
          {card.error}
        </div>
      )}
    </section>
  );
}
