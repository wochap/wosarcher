// Settings: "Run slots", the one limit for every run (PUT /api/settings `max_concurrent_runs`),
// and the slots in use (GET /api/slots, read on open and every 5 s).
import { Info, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { SlotState } from "../../api/types";
import { useApi } from "../../app/context";
import rows from "../../components/DomainRows.module.css";
import page from "../../components/Page.module.css";
import css from "./RunSlots.module.css";
import type { SettingsProps } from "./WritingDefaults";
import defaults from "./WritingDefaults.module.css";

export const SLOTS_POLL_MS = 5000;
export const MAX_RUNS = 8;

/** "1 web · 1 CLI · 1 queued", leaving out zero parts; every run not from the CLI counts as web. */
export function slotMix(slots: SlotState): string {
  const cli = slots.held.filter((h) => h.origin === "cli").length;
  const web = slots.held.length - cli;
  const parts: [number, string][] = [
    [web, "web"],
    [cli, "CLI"],
    [slots.queued.length, "queued"],
  ];
  return parts
    .filter(([n]) => n > 0)
    .map(([n, label]) => `${n} ${label}`)
    .join(" · ");
}

function valid(text: string): number | null {
  const value = Number(text);
  return Number.isInteger(value) && value >= 1 && value <= MAX_RUNS ? value : null;
}

export function RunSlots({ settings, setSettings }: SettingsProps) {
  const api = useApi();
  const [slots, setSlots] = useState<SlotState | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const read = () => api.getSlots().then(setSlots, () => {});
    void read();
    const timer = setInterval(read, SLOTS_POLL_MS);
    return () => clearInterval(timer);
  }, [api]);

  if (!settings) return null;
  const current = settings;
  const limit = current.max_concurrent_runs;
  const shown = text ?? String(limit);

  async function change(next: string) {
    setText(next);
    const value = valid(next);
    if (value === null || value === current.max_concurrent_runs) return;
    setError("");
    setSettings({ ...current, max_concurrent_runs: value });
    try {
      await api.putSettings({ ...current, max_concurrent_runs: value });
    } catch (e) {
      const message =
        e instanceof ApiError ? (e.fields.max_concurrent_runs ?? e.message) : String(e);
      setSettings((s) => s && { ...s, max_concurrent_runs: current.max_concurrent_runs });
      setText(null);
      setError(message);
    }
  }

  const held = slots?.held.length ?? 0;
  return (
    <>
      <div className={css.header}>
        <h2 className={page.section}>Run slots</h2>
        <span className={defaults.note}>Saved automatically</span>
      </div>
      <div className={`${page.panel} ${defaults.panel}`}>
        <div className={`${rows.row} ${rows.spacious}`}>
          <label htmlFor="set-maxruns" className={css.label}>
            Max concurrent runs
          </label>
          <div className={css.control}>
            <div className={css.field}>
              <input
                id="set-maxruns"
                className={`input ${css.input}`}
                type="number"
                min={1}
                max={MAX_RUNS}
                step={1}
                value={shown}
                aria-describedby="set-maxruns-h"
                onChange={(e) => void change(e.target.value)}
              />
              <span className={rows.hint}>runs at a time</span>
            </div>
            {error && (
              <span role="alert" className={rows.error}>
                <WarningCircle aria-hidden="true" className={rows.errorIcon} />
                {error}
              </span>
            )}
            <span id="set-maxruns-h" className={rows.hint}>
              One limit for every run on this server, whether it was started here, through the API
              or from the <span className={css.mono}>wosarcher</span> CLI. Extra runs wait in one
              queue, oldest first.
            </span>
            <div role="status" className={css.status}>
              <span className={css.bars} aria-hidden="true">
                {Array.from({ length: limit }, (_, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: one bar per slot, in order
                  <span key={i} className={css.bar} data-held={i < held} />
                ))}
              </span>
              <span>
                {held} of {limit} in use
              </span>
              {slots && <span className={css.mix}>{slotMix(slots)}</span>}
            </div>
            {valid(shown) === 1 && (
              <span className={css.note}>
                <Info aria-hidden="true" className={css.noteIcon} />
                Runs that are already going keep going. The lower limit applies as they finish.
              </span>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
