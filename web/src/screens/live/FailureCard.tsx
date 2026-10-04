// The Report panel's alert for a failed or interrupted run: the error, what is kept, and the
// ways on: retry from the failed stage, the same on the cloud profile, or copy the error.
import { ArrowClockwise, Copy, WarningOctagon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { ForkCreate } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { HelpTip } from "../../components/HelpTip";
import { PHASES, type PhaseId, type RunView } from "../../run/reducer";
import css from "./FailureCard.module.css";
import { INTERRUPTED, stageLabel, stoppedAt } from "./model";

function keptHint(stage: PhaseId): string {
  const earlier = PHASES.slice(0, PHASES.indexOf(stage));
  const retry = `Retry from ${stageLabel(stage)}, or run it again on the cloud profile.`;
  if (!earlier.length) return retry;
  if (earlier.length === 1) return `${stageLabel(earlier[0])} is cached. ${retry}`;
  return `${stageLabel(earlier[0])} through ${earlier.at(-1)} are cached. ${retry}`;
}

export function FailureCard({ run }: { run: RunView }) {
  const api = useApi();
  const { follow, toast } = useUi();
  const [cloud, setCloud] = useState(false);
  const stage = stoppedAt(run) ?? "plan";
  const error = run.failure?.error ?? INTERRUPTED;

  useEffect(() => {
    api.listProfiles().then(
      (profiles) => setCloud(profiles.some((p) => p.name === "cloud") && run.profile !== "cloud"),
      () => {},
    );
  }, [api, run.profile]);

  async function retry(body: ForkCreate) {
    try {
      const created = await api.forkRun(run.runId, body);
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function copy() {
    await navigator.clipboard?.writeText(error).catch(() => {});
    toast("Error copied");
  }

  return (
    <div role="alert" className={css.card}>
      <div className={css.title}>
        <WarningOctagon className={css.icon} aria-hidden="true" />
        Run failed at {stageLabel(stage)}
      </div>
      <pre className={css.error}>{error}</pre>
      <p className={css.hint}>{keptHint(stage)}</p>
      <div className={css.actions}>
        <span className={css.withHelp}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void retry({ from: stage })}
          >
            <ArrowClockwise aria-hidden="true" />
            Retry from {stageLabel(stage)}
          </button>
          <HelpTip help={stage === "score" ? "retry" : `retry-${stage}`} />
        </span>
        {cloud && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void retry({ from: stage, profile: "cloud" })}
          >
            Use cloud profile
          </button>
        )}
        <button type="button" className="btn btn-ghost" onClick={() => void copy()}>
          <Copy aria-hidden="true" />
          Copy error
        </button>
      </div>
    </div>
  );
}
