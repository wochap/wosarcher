// "Rewrite report": new writing options and model for a fork from the select stage, which
// reuses the run's sources and scored passages and picks the passages again.
import { CaretDown, CaretRight, PenNib, Recycle, X } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { RunDetail, WritingOptions } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { Dialog } from "../../components/Dialog";
import { ForkModelGroup } from "../../components/ForkModelGroup";
import { type WritingField, WritingOptionsForm } from "../../components/WritingOptionsForm";
import { changedCount, forkModelBase, forkModelPatch, initialState } from "../../run/forkModel";
import { overriddenFields } from "../new/OptionsPanel";
import css from "./RewriteDialog.module.css";

type Props = {
  run: RunDetail;
  sources: number;
  /** The passages the score stage kept: the selected ones plus those select skipped. */
  scored: number;
  nextVersion: number;
  onClose: () => void;
};

export function RewriteDialog({ run, sources, scored, nextVersion, onClose }: Props) {
  const api = useApi();
  const { follow, setLiveTab, toast } = useUi();
  const [value, setValue] = useState<WritingOptions>(run.writing);
  const [busy, setBusy] = useState(false);
  const base = useMemo(() => forkModelBase(run, "write"), [run]);
  const [model, setModel] = useState(() => initialState(base));
  const [modelOpen, setModelOpen] = useState(false);
  const changed = changedCount(model, base);
  const Caret = modelOpen ? CaretDown : CaretRight;

  async function confirm() {
    setBusy(true);
    try {
      const writing = overriddenFields(value, run.writing);
      const created = await api.forkRun(run.run_id, {
        from: "select",
        writing,
        ...forkModelPatch(model, base, "write"),
      });
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
          Reuses the {sources} sources and {scored} scored passages from this run. Passages are
          picked again for the model’s budget, then the report is written; no searching or fetching.
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
      <button
        type="button"
        className={`btn btn-ghost ${css.modelToggle}`}
        aria-expanded={modelOpen}
        onClick={() => setModelOpen(!modelOpen)}
      >
        <Caret aria-hidden="true" />
        Model
        {!modelOpen && changed > 0 && <span className={css.hint}>· {changed} changed</span>}
      </button>
      {modelOpen && (
        <ForkModelGroup
          run={run}
          step="write"
          withContextTokens
          words={value.words}
          base={base}
          value={model}
          onChange={setModel}
        />
      )}
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
          Rewrite from select stage
        </button>
      </div>
    </Dialog>
  );
}
