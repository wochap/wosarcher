// Confirm before cancelling a run not started in the browser: its CLI command or API caller
// gets the run back as cancelled (scenario `cancel-cli`).
import { Stop } from "@phosphor-icons/react";
import { Dialog } from "../../components/Dialog";
import css from "./CancelDialog.module.css";

type Props = {
  origin: "cli" | "api";
  tokenName?: string | null;
  onKeep: () => void;
  onCancel: () => void;
};

export function CancelDialog({ origin, tokenName, onKeep, onCancel }: Props) {
  const api = origin === "api";
  return (
    <Dialog
      role="alertdialog"
      title={api ? "Cancel this API run?" : "Cancel this CLI run?"}
      onClose={onKeep}
    >
      <div className={`dialog-body ${css.body}`}>
        <span>
          {api
            ? `It was started through the API with token “${tokenName ?? ""}”. The caller gets the run back as cancelled.`
            : "An agent started this run with the wosarcher CLI on this machine. Cancelling stops it for the agent too: its command exits and reports the run as cancelled."}
        </span>
        <span className={css.muted}>Completed stages are kept. Nothing is written.</span>
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={onKeep}>
          Keep running
        </button>
        <button type="button" className={`btn btn-secondary ${css.danger}`} onClick={onCancel}>
          <Stop aria-hidden="true" />
          Cancel run
        </button>
      </div>
    </Dialog>
  );
}
