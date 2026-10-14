// Time per stage: each phase card's time row and the stacked time bar, from the reducer's stage
// times. `now` is the browser time minus the view's clock offset.
import { capitalize as stageLabel } from "../components/tones";
import type { PhaseId, RunView } from "./reducer";

/** A wait for the device shorter than this is not shown. */
const MIN_WAIT = 0.05;

/** "14.4s" under a minute, "2m 05s" from a minute on. */
export function fmtDuration(seconds: number): string {
  const s = Math.max(0, seconds);
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${String(Math.floor(s % 60)).padStart(2, "0")}s`;
}

export type StageTime =
  | { kind: "none" }
  | { kind: "skipped" }
  | { kind: "waiting"; wait: number }
  | {
      kind: "time";
      seconds: number;
      /** Each round's seconds, the running one last. */
      rounds: number[];
      wait: number;
      live: boolean;
      failed: boolean;
    };

const since = (ts: string, now: number) => Math.max(0, (now - Date.parse(ts)) / 1000);
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);

/** One stage's time; `skipped` comes from the card (a skipped stage or one the recipe skips). */
export function stageTime(run: RunView, id: PhaseId, skipped: boolean, now: number): StageTime {
  const phase = run.phases[id];
  if (skipped) return { kind: "skipped" };
  if (phase.state === "waiting")
    return { kind: "waiting", wait: phase.waitTs ? since(phase.waitTs, now) : 0 };
  if (phase.state === "pending" || phase.state === "reused") return { kind: "none" };
  const live = phase.state === "running";
  const end = live || !run.endedAt ? now : Date.parse(run.endedAt);
  const open = phase.startedTs ? [since(phase.startedTs, end)] : [];
  const rounds = [...phase.seconds, ...open];
  return {
    kind: "time",
    seconds: sum(rounds),
    rounds,
    wait: sum(phase.waits),
    live,
    failed: phase.state === "failed",
  };
}

/** The time row: its text, the GPU wait chip, and its title. */
export type TimeRow = {
  text: string;
  wait: string;
  title: string;
  tone: "faint" | "accent" | "danger" | "muted";
};

export function timeRow(time: StageTime): TimeRow {
  switch (time.kind) {
    case "none":
      return { text: "—", wait: "", title: "", tone: "faint" };
    case "skipped":
      return { text: "skipped", wait: "", title: "Skipped", tone: "faint" };
    case "waiting":
      return {
        text: "—",
        wait: fmtDuration(time.wait),
        title: `Waiting for the GPU · ${fmtDuration(time.wait)}`,
        tone: "faint",
      };
    case "time": {
      const wait = time.wait >= MIN_WAIT ? `+${fmtDuration(time.wait)}` : "";
      const head =
        time.rounds.length > 1
          ? `${time.rounds.map((r, n) => `Round ${n + 1} ${fmtDuration(r)}`).join(" · ")} · total `
          : "Stage time ";
      const plus = wait ? ` · plus ${fmtDuration(time.wait)} waiting for the GPU` : "";
      return {
        text: fmtDuration(time.seconds),
        wait,
        title: `${head}${fmtDuration(time.seconds)}${plus}`,
        tone: time.live ? "accent" : time.failed ? "danger" : "muted",
      };
    }
  }
}

export type BarKind = "queue" | "wait" | PhaseId;
export type BarPart = { kind: BarKind; label: string; seconds: number; title: string };
export type TopPart = { kind: BarKind; label: string; time: string; pct: string };
export type ListItem = {
  kind: BarKind;
  label: string;
  time: string;
  pct: string;
  note: string;
  skipped: boolean;
};

export type TimeBar = {
  total: number;
  running: boolean;
  parts: BarPart[];
  top: TopPart[];
  all: ListItem[];
  aria: string;
};

/** The time section: the queue, each wait before its stage, and each stage that ran. */
export function timeBar(
  run: RunView,
  phases: readonly PhaseId[],
  skippedOf: (id: PhaseId) => boolean,
  created: string | undefined,
  now: number,
): TimeBar {
  const queue =
    created && run.startedAt
      ? Math.max(0, (Date.parse(run.startedAt) - Date.parse(created)) / 1000)
      : 0;
  const times = Object.fromEntries(
    phases.map((id) => [id, stageTime(run, id, skippedOf(id), now)]),
  ) as Record<PhaseId, StageTime>;
  const raw: Omit<BarPart, "title">[] = [];
  if (queue > 0) raw.push({ kind: "queue", label: "Queue", seconds: queue });
  let waited = 0;
  const waitedBefore: string[] = [];
  for (const id of phases) {
    const time = times[id];
    if (time.kind === "waiting" && time.wait >= MIN_WAIT) {
      waited += time.wait;
      waitedBefore.push(stageLabel(id));
      raw.push({ kind: "wait", label: `GPU wait before ${stageLabel(id)}`, seconds: time.wait });
    }
    if (time.kind !== "time") continue;
    if (time.wait >= MIN_WAIT) {
      waited += time.wait;
      waitedBefore.push(stageLabel(id));
      raw.push({ kind: "wait", label: `GPU wait before ${stageLabel(id)}`, seconds: time.wait });
    }
    if (time.seconds > 0 || time.live)
      raw.push({ kind: id, label: stageLabel(id), seconds: time.seconds });
  }
  const total = sum(raw.map((p) => p.seconds));
  const pct = (seconds: number) => {
    if (!total) return "";
    const share = (seconds / total) * 100;
    return share > 0 && share < 1 ? "<1%" : `${Math.round(share)}%`;
  };
  const parts = raw.map((p) => ({
    ...p,
    title: `${p.label} · ${fmtDuration(p.seconds)} · ${pct(p.seconds)}`,
  }));
  const ranked: Omit<BarPart, "title">[] = raw.filter((p) => p.kind !== "wait");
  if (waited) ranked.push({ kind: "wait", label: "GPU wait", seconds: waited });
  const top = ranked
    .sort((a, b) => b.seconds - a.seconds)
    .slice(0, 3)
    .map((p) => ({
      kind: p.kind,
      label: p.label,
      time: fmtDuration(p.seconds),
      pct: pct(p.seconds),
    }));
  const all: ListItem[] = [];
  if (queue > 0)
    all.push({
      kind: "queue",
      label: "Queue",
      time: fmtDuration(queue),
      pct: pct(queue),
      note: "waiting for a free run slot",
      skipped: false,
    });
  for (const id of phases) {
    const time = times[id];
    const label = stageLabel(id);
    if (time.kind === "skipped")
      all.push({ kind: id, label, time: "skipped", pct: "", note: "", skipped: true });
    else if (time.kind === "time")
      all.push({
        kind: id,
        label: time.live ? `${label} · running` : label,
        time: fmtDuration(time.seconds),
        pct: pct(time.seconds),
        note: time.rounds.length > 1 ? time.rounds.map(fmtDuration).join(" + ") : "",
        skipped: false,
      });
  }
  if (waited)
    all.push({
      kind: "wait",
      label: "GPU wait",
      time: fmtDuration(waited),
      pct: pct(waited),
      note: `before ${waitedBefore.join(", ")}`,
      skipped: false,
    });
  return {
    total,
    running: run.status === "running",
    parts,
    top,
    all,
    aria: `Time per stage, ${fmtDuration(total)} total: ${parts.map((p) => p.title).join("; ")}`,
  };
}
