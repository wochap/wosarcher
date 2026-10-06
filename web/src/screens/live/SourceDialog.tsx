// One source of the run as its stored chunks, each with its fate badge and score; the selected
// chunk's fate, why line, and sub-query chips sit in the header. Opened from a passage card.
import {
  ArrowSquareOut,
  CaretDown,
  CaretUp,
  CircleNotch,
  FileText,
  GlobeSimple,
  Paperclip,
  Scissors,
  X,
} from "@phosphor-icons/react";
import { type KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import type { Context } from "../../api/generated";
import type { SourceChunk, SourceView, WritingOptions } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { Dialog } from "../../components/Dialog";
import { label, site } from "../../run/citations";
import { badgeOf, chipText, whyLine } from "../../run/sourceFates";
import { FateBadge } from "./PassagesPanel";
import css from "./SourceDialog.module.css";

type Props = {
  runId: string;
  sourceId: string;
  /** The chunk selected on open. */
  chunkId: string;
  /** Changes when the view should be fetched again (a stage finished); the selection stays. */
  reloadKey?: string | number;
  marker: WritingOptions["citation_marker"];
  context: Context | null;
  prefilterTopK?: number;
  onClose: () => void;
};

const SKELETON = ["92%", "84%", "88%", "76%", "90%"];
const fixed = (n: number) => n.toFixed(2);
const typing = (target: EventTarget | null) =>
  /^(INPUT|TEXTAREA|SELECT)$/.test((target as HTMLElement | null)?.tagName ?? "");

function useSourceView(runId: string, sourceId: string, reloadKey: Props["reloadKey"]) {
  const api = useApi();
  const [view, setView] = useState<SourceView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: reloadKey and attempt refetch.
  useEffect(() => {
    let current = true;
    setError(null);
    api.source(runId, sourceId).then(
      (found) => current && setView(found),
      (e: Error) => current && setError(e.message),
    );
    return () => {
      current = false;
    };
  }, [api, runId, sourceId, reloadKey, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { view, error, retry };
}

function ChunkBlock(props: {
  chunk: SourceChunk;
  view: SourceView;
  selected: boolean;
  heading: string;
  cite: (n: number) => string;
  onSelect: () => void;
}) {
  const { chunk, view, selected, heading, cite, onSelect } = props;
  const fate = chunk.fate;
  const scored = fate.display != null && fate.kind !== "pending";
  const sub = chunk.heading_path?.slice(1).join(" › ") ?? "";
  const mark = fate.kind === "cited" && fate.n != null ? cite(fate.n) : "";
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    onSelect();
  };
  return (
    <>
      {heading && <h3 className={css.heading}>{heading}</h3>}
      {chunk.removed_before ? (
        <div className={css.removed}>{chunk.removed_before} near-duplicate chunks removed</div>
      ) : null}
      {/* biome-ignore lint/a11y/useSemanticElements: a block of text that selects itself. */}
      <div
        role="button"
        tabIndex={0}
        className={css.chunk}
        data-chunk={chunk.chunk_id}
        data-selected={selected || undefined}
        aria-current={selected || undefined}
        aria-label={`${scored ? `${fixed(fate.display ?? 0)}, ` : ""}${fate.kind}${mark ? ` ${mark}` : ""}. ${chunk.heading_path?.join(" › ") ?? ""}`}
        onClick={onSelect}
        onKeyDown={onKey}
      >
        <div className={css.chunkInner}>
          <div className={css.chunkHead}>
            <FateBadge
              fate={badgeOf(fate)}
              threshold={view.threshold}
              mark={mark}
              queryId={fate.query_id}
              className={css.badge}
            />
            {scored && <span className={css.chunkScore}>{fixed(fate.display ?? 0)}</span>}
            {chunk.floor && <span className={css.floor}>best available</span>}
            {sub && <span className={css.sub}>{sub}</span>}
          </div>
          <p className={css.text}>{chunk.text}</p>
        </div>
      </div>
    </>
  );
}

function FateBlock(props: {
  chunk: SourceChunk;
  view: SourceView;
  cite: (n: number) => string;
  prefilterTopK?: number;
}) {
  const { chunk, view, cite } = props;
  const fate = chunk.fate;
  const scored = fate.display != null && fate.kind !== "pending";
  const above = scored && view.threshold != null && (fate.display ?? 0) >= view.threshold;
  return (
    <div className={css.fate} aria-live="polite">
      <div className={css.fateHead}>
        <FateBadge
          fate={badgeOf(fate)}
          threshold={view.threshold}
          mark={fate.kind === "cited" && fate.n != null ? cite(fate.n) : ""}
          queryId={fate.query_id}
          className={css.badge}
        />
        {scored && (
          <span className={css.score} data-above={above || undefined}>
            {fixed(fate.display ?? 0)}
          </span>
        )}
        {chunk.floor && <span className={css.floor}>best available</span>}
        <span className={css.path}>{chunk.heading_path?.join(" › ")}</span>
      </div>
      <div className={css.why}>{whyLine(fate, view, cite, props.prefilterTopK)}</div>
      <ul className={css.chips} aria-label="Sub-queries">
        {chunk.queries.map((row) => {
          const query = view.queries.find((q) => q.id === row.query_id);
          return (
            <li
              key={row.query_id}
              className={css.chip}
              data-primary={row.query_id === fate.query_id || undefined}
              title={query ? `${query.id}: ${query.text}` : row.query_id}
            >
              <span className={css.chipId}>{row.query_id}</span>
              {row.display != null && row.state !== "pending" && (
                <span className={css.chipScore}>{fixed(row.display)}</span>
              )}
              {chipText(row, fate, view.threshold)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SourceDialog(props: Props) {
  const { runId, sourceId, marker, context, onClose } = props;
  const { isPhone } = useUi();
  const { view, error, retry } = useSourceView(runId, sourceId, props.reloadKey);
  const [chunkId, setChunkId] = useState(props.chunkId);
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const chunks = view?.chunks ?? [];
  const found = chunks.findIndex((c) => c.chunk_id === chunkId);
  const index = found < 0 ? 0 : found;
  const selected = chunks[index];
  const cite = (n: number) => label(n, marker, context);

  useEffect(() => panel.current?.focus(), []);
  useEffect(() => {
    if (!selected) return;
    const element = body.current?.querySelector(`[data-chunk="${selected.chunk_id}"]`);
    element?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  const move = (step: number) => {
    const next = chunks[index + step];
    if (next) setChunkId(next.chunk_id);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!/^Arrow(Up|Down|Left|Right)$/.test(e.key) || typing(e.target) || !view) return;
    e.preventDefault();
    e.stopPropagation();
    move(/Down|Right/.test(e.key) ? 1 : -1);
  };

  const source = view?.source;
  const isFile = source?.kind === "file";
  const SourceIcon = isFile ? FileText : GlobeSimple;
  const scored = chunks.filter((c) => !["pre", "pending"].includes(badgeOf(c.fate))).length;
  const cited = chunks.filter((c) => c.fate.kind === "cited").length;
  const loading = !view && !error;
  let previousTop = "";

  return (
    <Dialog
      labelledBy={titleId}
      onClose={onClose}
      onKeyDown={onKeyDown}
      panelRef={panel}
      className={`${css.dialog} ${isPhone ? css.sheet : ""}`}
    >
      <header className={css.header}>
        <div className={css.titleRow}>
          <SourceIcon aria-hidden="true" className={css.icon} />
          <div className={css.titles}>
            <div id={titleId} className={css.title}>
              {source?.title ?? "Source"}
            </div>
            {source && (
              <div className={css.meta}>
                <span className={css.domain}>{site(source)}</span>
                {isFile ? (
                  <span className={css.inline}>
                    <Paperclip aria-hidden="true" />
                    Attached file · no URL
                  </span>
                ) : (
                  <a href={source.uri} target="_blank" rel="noreferrer" className={css.inline}>
                    Open original
                    <ArrowSquareOut aria-hidden="true" />
                  </a>
                )}
                <span>
                  {chunks.length} chunks · {scored} scored · {cited} cited
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            className={`btn btn-ghost btn-icon ${css.close}`}
            aria-label="Close source"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </div>
        {view?.truncated && (
          <div role="note" className={css.truncated}>
            <Scissors aria-hidden="true" className={css.warnIcon} />
            <span>
              Fetch stopped at the character limit. Text after this point was not scraped.
            </span>
          </div>
        )}
        {loading && (
          <div className={css.loading}>
            <CircleNotch aria-hidden="true" className={css.spinner} />
            Loading cleaned text…
          </div>
        )}
        {error && (
          <div role="alert" className={css.error}>
            <span>{error}</span>
            <button type="button" className="btn btn-secondary" onClick={retry}>
              Retry
            </button>
          </div>
        )}
        {view && selected && (
          <FateBlock chunk={selected} view={view} cite={cite} prefilterTopK={props.prefilterTopK} />
        )}
      </header>
      <div ref={body} className={css.body}>
        {loading &&
          SKELETON.map((width) => (
            <div key={width} className={css.skeleton} data-testid="source-skeleton">
              <div className={css.skeletonHead} />
              <div className={css.skeletonLine} style={{ width }} />
              <div className={css.skeletonShort} />
            </div>
          ))}
        {view &&
          chunks.map((chunk, i) => {
            const top = chunk.heading_path?.[0] ?? "";
            const heading = top !== previousTop ? top : "";
            previousTop = top;
            return (
              <ChunkBlock
                key={chunk.chunk_id}
                chunk={chunk}
                view={view}
                selected={i === index}
                heading={heading}
                cite={cite}
                onSelect={() => setChunkId(chunk.chunk_id)}
              />
            );
          })}
        {view?.truncated && (
          <div className={css.truncEnd}>
            <Scissors aria-hidden="true" />
            Fetch stopped here
          </div>
        )}
      </div>
      <footer className={css.footer}>
        <span>{view ? `Chunk ${chunks.length ? index + 1 : 0} of ${chunks.length}` : ""}</span>
        {!isPhone && (
          <span className={css.keys}>
            <kbd>↑</kbd>
            <kbd>↓</kbd>
            move
            <kbd className={css.esc}>Esc</kbd>
            close
          </span>
        )}
        <div className={css.nav}>
          <button
            type="button"
            className={`btn btn-secondary ${css.navButton}`}
            disabled={!view || index <= 0}
            onClick={() => move(-1)}
          >
            <CaretUp aria-hidden="true" />
            Prev
          </button>
          <button
            type="button"
            className={`btn btn-secondary ${css.navButton}`}
            disabled={!view || index >= chunks.length - 1}
            onClick={() => move(1)}
          >
            Next
            <CaretDown aria-hidden="true" />
          </button>
        </div>
      </footer>
    </Dialog>
  );
}
