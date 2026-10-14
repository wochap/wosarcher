// Confirm deleting a user depth preset or profile (scenario `new-delete`).
import { Trash } from "@phosphor-icons/react";
import { Dialog } from "../../components/Dialog";
import type { PresetKind } from "../../run/presets";
import css from "./SaveDialog.module.css";

type Props = {
  kind: PresetKind;
  name: string;
  /** What the selection switches to when the item is selected, e.g. " Depth switches to Standard." */
  switchNote: string;
  onConfirm: () => void;
  onClose: () => void;
};

export function DeleteDialog({ kind, name, switchNote, onConfirm, onClose }: Props) {
  return (
    <Dialog role="alertdialog" title={`Delete ${kind} “${name}”?`} onClose={onClose}>
      <div className="dialog-body">
        Runs that used it keep the values they ran with.{switchNote} This can’t be undone.
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className={`btn btn-secondary ${css.danger}`} onClick={onConfirm}>
          <Trash aria-hidden="true" />
          Delete {kind}
        </button>
      </div>
    </Dialog>
  );
}
