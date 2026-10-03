// A run's status as the prototype's History tags: icon and tint per status.
import { Check, CircleNotch, type Icon, StopCircle, XCircle } from "@phosphor-icons/react";
import type { RunStatus } from "../api/types";
import css from "./StatusTag.module.css";

const LOOK: Record<RunStatus, { label: string; icon: Icon; spin?: boolean }> = {
  done: { label: "Completed", icon: Check },
  running: { label: "Running", icon: CircleNotch, spin: true },
  queued: { label: "Queued", icon: CircleNotch, spin: true },
  failed: { label: "Failed", icon: XCircle },
  interrupted: { label: "Interrupted", icon: XCircle },
  cancelled: { label: "Cancelled", icon: StopCircle },
};

export function StatusTag({ status }: { status: RunStatus }) {
  const look = LOOK[status];
  const Glyph = look.icon;
  return (
    <span className={`tag ${css.status}`} data-state={status}>
      <Glyph className={look.spin ? "spin" : undefined} aria-hidden="true" />
      {look.label}
    </span>
  );
}
