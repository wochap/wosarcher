// The header's device chip: the device of the running stage, or the one a stage waits for.
// Labels only; no source reports memory figures.
import { Cpu } from "@phosphor-icons/react";
import { HelpTip } from "../../components/HelpTip";
import { PHASES, type RunView } from "../../run/reducer";
import css from "./LiveHeader.module.css";

export function deviceLabel(run: RunView): { text: string; tone: "busy" | "wait" | "idle" } | null {
  const phases = PHASES.map((id) => ({ id, ...run.phases[id] }));
  const busy = phases.find((p) => p.state === "running" && p.device);
  if (busy) return { text: busy.device ?? "", tone: "busy" };
  const waiting = phases.find((p) => p.state === "waiting" && p.device);
  if (waiting) return { text: `${waiting.device} · waiting`, tone: "wait" };
  const last = phases.filter((p) => p.device).at(-1);
  return last ? { text: last.device ?? "", tone: "idle" } : null;
}

export function DeviceChip({ run }: { run: RunView }) {
  const label = deviceLabel(run);
  if (!label) return null;
  return (
    <span className={css.chip}>
      <Cpu className={css.chipIcon} data-tone={label.tone} aria-hidden="true" />
      <span className={css.chipLabel}>{label.text}</span>
      <HelpTip help="device" />
    </span>
  );
}
