// A run the server does not know: the empty state's layout with its own icon and text.
import { Plus, Question } from "@phosphor-icons/react";
import { go } from "../../app/route";
import css from "./EmptyLive.module.css";

export function NotFound({ runId }: { runId: string }) {
  return (
    <div className={css.empty}>
      <Question className={css.icon} aria-hidden="true" />
      <h2 className={css.title}>Run not found</h2>
      <p className={css.text}>
        Run {runId} does not exist on this server. It may have been deleted.
      </p>
      <button type="button" className="btn btn-primary" onClick={() => go({ screen: "new" })}>
        <Plus aria-hidden="true" />
        New run<span className={css.hint}>Alt 1</span>
      </button>
    </div>
  );
}
