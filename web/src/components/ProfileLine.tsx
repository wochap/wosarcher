// The profile line of the Live run and Report headers: the profile and the entries the run used,
// the llm entry with its model. A phone shows the profile and the llm until "All providers".
import { CaretDown, CaretUp, Stack } from "@phosphor-icons/react";
import { useState } from "react";
import type { RunSummary } from "../api/types";
import { BLOCKS } from "../run/profileValues";
import css from "./ProfileLine.module.css";
import { Tag } from "./Tag";

type Props = {
  run: Pick<RunSummary, "profile" | "use" | "model" | "modified">;
  isPhone: boolean;
};

export function ProfileLine({ run, isPhone }: Props) {
  const [open, setOpen] = useState(false);
  const use = run.use;
  if (!use) return null;
  const llm = run.model ? `${use.llm ?? ""}/${run.model}` : (use.llm ?? "");
  const all = BLOCKS.flatMap((b) => (b === "llm" ? [llm] : use[b] ? [use[b]] : [])).join(" · ");
  const Caret = open ? CaretUp : CaretDown;
  return (
    <div className={css.line}>
      <Stack className={css.icon} aria-hidden="true" />
      <span className={css.name}>{run.profile}</span>
      <span aria-hidden="true">·</span>
      <span className={css.entries}>{isPhone && !open ? llm : all}</span>
      {run.modified && (
        <Tag variant="outline" small>
          modified
        </Tag>
      )}
      {isPhone && (
        <button
          type="button"
          className={`btn btn-ghost ${css.toggle}`}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <Caret aria-hidden="true" />
          {open ? "Fewer" : "All providers"}
        </button>
      )}
    </div>
  );
}
