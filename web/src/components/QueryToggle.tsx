// The "Show full question · N characters" toggle after a query longer than 240 characters.
import { CaretDown, CaretUp } from "@phosphor-icons/react";
import { fmtN } from "../run/depth";
import css from "./QueryToggle.module.css";

/** Queries longer than this are clamped and get the toggle. */
export const LONG_QUERY_CHARS = 240;

export const isLongQuery = (query: string) => query.length > LONG_QUERY_CHARS;

type Props = {
  query: string;
  open: boolean;
  /** The id of the element showing the query. */
  controls: string;
  onToggle: () => void;
};

export function QueryToggle({ query, open, controls, onToggle }: Props) {
  const Caret = open ? CaretUp : CaretDown;
  return (
    <button
      type="button"
      className={`btn btn-ghost ${css.toggle}`}
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
    >
      <Caret aria-hidden="true" />
      {open ? "Show less" : "Show full question"}
      <span className={css.count}>· {fmtN(query.length)} characters</span>
    </button>
  );
}
