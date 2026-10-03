// The header's device chip: which stage holds the device, or that models are swapping. Labels
// only; no source reports memory figures.
import { Cpu } from "@phosphor-icons/react";
import { PHASES, type RunView } from "../../run/reducer";
import css from "./LiveHeader.module.css";

export function deviceLabel(run: RunView): { text: string; tone: "busy" | "wait" | "idle" } | null {
  const phases = PHASES.map((id) => ({ id, ...run.phases[id] }));
  const busy = phases.find((p) => p.state === "running" && p.device);
  if (busy) return { text: `${busy.id} · ${busy.device}`, tone: "busy" };
  const waiting = phases.find((p) => p.state === "waiting" && p.device);
  if (waiting) return { text: `${waiting.device} · swapping models`, tone: "wait" };
  const last = phases.filter((p) => p.device).at(-1);
  return last ? { text: `${last.device} · idle`, tone: "idle" } : null;
}

export function DeviceChip({ run }: { run: RunView }) {
  const label = deviceLabel(run);
  if (!label) return null;
  return (
    <span className={css.chip} title="The device the current stage runs on">
      <Cpu className={css.chipIcon} data-tone={label.tone} aria-hidden="true" />
      {label.text}
    </span>
  );
}
