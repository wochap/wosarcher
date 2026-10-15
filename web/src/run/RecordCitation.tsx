// Record citations of a catalog report: each passage renders one record (name, type, then
// `field: value` lines) and carries its record ID. Hovering or focusing a chip shows the
// record popover, which stays open while the pointer is on it; pressing the chip or "Open
// record" opens the record's drawer on the Catalog result screen.
import { SidebarSimple } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Context, Passage } from "../api/generated";
import type { WritingOptions } from "../api/types";
import { useUi } from "../app/context";
import { go } from "../app/route";
import type { Cite } from "./CitationTooltip";
import { tooltipPlace } from "./CitationTooltip";
import { label } from "./citations";
import css from "./RecordCitation.module.css";

const HIDE_MS = 150;

export type RecordView = {
  id: string;
  name: string;
  type: string;
  fields: { key: string; value: string }[];
};

/** The record a passage renders, or null for a passage without a record ID. */
export function recordOf(passage: Passage): RecordView | null {
  if (!passage.record_id) return null;
  const [name = "", type = "", ...lines] = passage.text.split("\n");
  const fields = lines.map((line) => {
    const at = line.indexOf(": ");
    return at < 0
      ? { key: "", value: line }
      : { key: line.slice(0, at), value: line.slice(at + 2) };
  });
  return { id: passage.record_id, name, type, fields };
}

/** True when the context's passages are catalog records. */
export const isRecordContext = (context: Context | null) =>
  !!context?.passages.some((p) => p.record_id);

/** Opens the record's drawer on the Catalog result screen of `runId`. */
export function openRecord(runId: string, record: string) {
  go({ screen: "catalog", runId, records: true, record });
}

/** The shown record citation; leaving the chip hides it after a moment unless the pointer
 * moves onto the popover. Escape hides it through the overlay stack. */
export function useRecordCitation() {
  const { overlay } = useUi();
  const [cite, setCite] = useState<Cite | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const keep = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);
  const hide = useCallback(() => {
    keep();
    setCite(null);
  }, [keep]);
  const onCite = useCallback(
    (n: number, rect: DOMRect) => {
      keep();
      setCite({ n, rect });
    },
    [keep],
  );
  const onLeave = useCallback(() => {
    keep();
    timer.current = setTimeout(() => setCite(null), HIDE_MS);
  }, [keep]);
  useEffect(() => (cite ? overlay("tooltip", hide) : undefined), [cite, overlay, hide]);
  useEffect(() => keep, [keep]);
  return { cite, onCite, onLeave, keep, hide };
}

type Props = {
  cite: Cite | null;
  context: Context | null;
  marker: WritingOptions["citation_marker"];
  onOpen: (record: string) => void;
  onKeep: () => void;
  onLeave: () => void;
};

export function RecordPopover({ cite, context, marker, onOpen, onKeep, onLeave }: Props) {
  if (!cite || !context) return null;
  const passage = context.passages.find((p) => p.n === cite.n);
  const record = passage && recordOf(passage);
  if (!passage || !record) return null;
  const place = tooltipPlace(cite.rect);
  return (
    <div
      role="tooltip"
      className={css.popover}
      data-above={place.above}
      style={{ left: place.left, top: place.top }}
      onMouseEnter={onKeep}
      onMouseLeave={onLeave}
    >
      <div className={css.head}>
        <span className={css.label}>{label(passage.n, marker, context)}</span>
        <span className={`tag tag-neutral ${css.type}`}>{record.type}</span>
        <span className={css.id}>{record.id}</span>
      </div>
      <span className={css.name}>{record.name}</span>
      {record.fields.length > 0 && (
        <div className={css.fields}>
          <span className={css.citedFor}>Cited for</span>
          {record.fields.map((f) => (
            <div key={`${f.key}:${f.value}`} className={css.field}>
              <span className={css.key}>{f.key}</span>
              <span className={css.value}>{f.value}</span>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        className={`btn btn-ghost ${css.open}`}
        onClick={() => onOpen(record.id)}
      >
        <SidebarSimple aria-hidden="true" />
        Open record
      </button>
    </div>
  );
}
