// Live run with nothing to follow.
import { Plus, Pulse } from "@phosphor-icons/react";
import { go } from "../../app/route";
import css from "./EmptyLive.module.css";

export function EmptyLive() {
  return (
    <div className={css.empty}>
      <Pulse className={css.icon} aria-hidden="true" />
      <h2 className={css.title}>No run in progress</h2>
      <p className={css.text}>
        Start a run to watch each stage live: planning, search, fetching, scoring and the report as
        it is written.
      </p>
      <button type="button" className="btn btn-primary" onClick={() => go({ screen: "new" })}>
        <Plus aria-hidden="true" />
        New run<span className={css.hint}>Alt 1</span>
      </button>
    </div>
  );
}
