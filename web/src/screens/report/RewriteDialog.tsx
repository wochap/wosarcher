// "Rewrite report": new writing options for a fork from the write stage, which reuses the
// run's sources and passages.
import { PenNib, Recycle, X } from "@phosphor-icons/react";
import { useState } from "react";
import type { RunDetail, WritingOptions } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { Dialog } from "../../components/Dialog";
import { type WritingField, WritingOptionsForm } from "../../components/WritingOptionsForm";
import { overriddenFields } from "../new/OptionsPanel";
import css from "./RewriteDialog.module.css";

type Props = {
  run: RunDetail;
  sources: number;
  passages: number;
  nextVersion: number;
  onClose: () => void;
};

export function RewriteDialog({ run, sources, passages, nextVersion, onClose }: Props) {
  const api = useApi();
  const { follow, setLiveTab, toast } = useUi();
  const [value, setValue] = useState<WritingOptions>(run.writing);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      const writing = overriddenFields(value, run.writing);
      const created = await api.forkRun(run.run_id, { from: "write", writing });
      follow(created.run_id);
      setLiveTab("report");
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      toast((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Dialog title="Rewrite report" onClose={onClose} className={css.dialog}>
      <PenNib className={css.titleIcon} aria-hidden="true" />
      <button
        type="button"
        className={`btn btn-ghost btn-icon ${css.close}`}
        aria-label="Close"
        onClick={onClose}
      >
        <X aria-hidden="true" />
      </button>
      <div className={css.note}>
        <Recycle className={css.noteIcon} aria-hidden="true" />
        <span>
          Reuses the {sources} sources and {passages} selected passages from this run. Only the
          write stage runs again; no searching or fetching.
        </span>
      </div>
      <WritingOptionsForm
        idPrefix="rw"
        value={value}
        base={run.writing}
        mark="changed"
        baseLabel="was "
        compact
        withFormat
        onChange={<F extends WritingField>(field: F, v: WritingOptions[F]) =>
          setValue((w) => ({ ...w, [field]: v }))
        }
      />
      <div className={`dialog-actions ${css.actions}`}>
        <span className={css.creates}>
          Creates <span className={css.mono}>v{nextVersion}</span> linked to{" "}
          <span className={css.mono}>{run.run_id}</span>
        </span>
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void confirm()}
        >
          <PenNib aria-hidden="true" />
          Rewrite from write stage
        </button>
      </div>
    </Dialog>
  );
}
