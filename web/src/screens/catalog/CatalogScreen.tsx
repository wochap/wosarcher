// The Catalog result screen (`#/catalog/<id>`, scenario `catalog-result`): header and actions,
// the Table, Graph, and JSON views, the Summary aside, the record drawer, and the fork dialogs.
// A research run's ID shows the Report screen instead.
import {
  ArrowsClockwise,
  BracketsCurly,
  Check,
  CheckCircle,
  Copy,
  DownloadSimple,
  FileCsv,
  FunnelX,
  Graph as GraphIcon,
  Link,
  MagnifyingGlass,
  Table,
  TreeStructure,
  Warning,
  X,
} from "@phosphor-icons/react";
import { type KeyboardEvent, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { Catalog, CatalogRecord, RunDetail, Structure } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { Dialog } from "../../components/Dialog";
import { HelpTip } from "../../components/HelpTip";
import { dateTime } from "../../format";
import { LIMITS, limitsOf, shortField, typesOf } from "../../run/catalog";
import {
  byDepth,
  catalogCsv,
  columnsOf,
  depths,
  type Filters,
  filterRecords,
  flagsOf,
  graphLabel,
  graphLayout,
  idOf,
  NO_FILTERS,
  nameOf,
  pagesOf,
  recordsJson,
  sourceUrls,
  typeOf,
  worstFilled,
} from "../../run/catalogResult";
import { fmtDuration } from "../../run/stageTimes";
import { EFFORT_LABELS, EFFORTS } from "../../run/thinking";
import { NotFound } from "../live/NotFound";
import { download } from "../report/exportReport";
import { ReportScreen } from "../report/ReportScreen";
import css from "./CatalogScreen.module.css";

/** Type colours of the graph and the type chips, in the order the types are listed. */
export const TYPE_COLORS = [
  "var(--color-accent-200)",
  "var(--color-accent)",
  "var(--color-accent-700)",
  "var(--color-neutral-300)",
  "var(--color-neutral-500)",
  "var(--color-neutral-700)",
];

type View = "table" | "graph" | "json";
type Props = { runId: string; detail?: RunDetail };

export function CatalogScreen({ runId, detail: given }: Props) {
  const api = useApi();
  const [detail, setDetail] = useState<RunDetail | null>(given ?? null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [structure, setStructure] = useState<Structure | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (given) return;
    api.getRun(runId).then(setDetail, (e) => {
      if (e instanceof ApiError && e.status === 404) setMissing(true);
    });
  }, [api, runId, given]);

  const catalogRun = detail?.kind === "catalog";
  useEffect(() => {
    if (!catalogRun) return;
    api.getArtifact(runId, "catalog.json").then(
      (text) => setCatalog(JSON.parse(text) as Catalog),
      () => setCatalog({ records: [], nodes: 0, reason: "frontier empty" }),
    );
    api.getArtifact(runId, "structure.json").then(
      (text) => setStructure(JSON.parse(text) as Structure),
      () => {},
    );
  }, [api, runId, catalogRun]);

  if (missing) return <NotFound runId={runId} />;
  if (!detail) return null;
  if (!catalogRun) return <ReportScreen runId={runId} />;
  if (!catalog) return null;
  return <CatalogResult detail={detail} catalog={catalog} structure={structure} />;
}

type ResultProps = { detail: RunDetail; catalog: Catalog; structure: Structure | null };

function CatalogResult({ detail, catalog, structure }: ResultProps) {
  const { toast, isPhone } = useUi();
  const [view, setView] = useState<View>("table");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"expand" | "reextract" | null>(null);
  const records = catalog.records;
  const fields = columnsOf(structure, records);
  const types = [
    ...new Set([...typesOf(structure), ...records.map((r) => typeOf(r, fields))]),
  ].filter((t) => records.some((r) => typeOf(r, fields) === t));
  const color = (type: string) => TYPE_COLORS[Math.max(0, types.indexOf(type)) % 6];
  const byId = new Map(records.map((r) => [idOf(r, fields), r]));
  const shown = filterRecords(records, fields, filters);
  const n = records.length;
  const sel = selected ? byId.get(selected) : undefined;
  const depthOf = depths(records, fields);

  const meta = [
    dateTime(detail.created),
    detail.duration_s == null ? "–" : fmtDuration(detail.duration_s),
    "catalog",
    `${n} nodes`,
    `${sourceUrls(records).length} sources`,
  ].join(" · ");

  async function copyJson() {
    await navigator.clipboard?.writeText(recordsJson(records)).catch(() => {});
    toast(`Copied JSON · ${n} records`);
  }
  const save = (name: string, text: string, type: string) => {
    download(name, new Blob([text], { type }));
    toast(`Downloaded ${name}`);
  };
  const setFilter = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className={css.screen}>
      <div className={css.page}>
        <div className={css.inner}>
          <header className={css.header}>
            <div className={css.line}>
              <span className={`tag tag-neutral ${css.done}`}>
                <Check aria-hidden="true" />
                Completed
              </span>
              <span className={css.id}>{detail.run_id}</span>
              <span>{meta}</span>
            </div>
            <h1 className={css.h1}>{detail.query}</h1>
            <div className={css.actions}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => save("catalog.json", recordsJson(records), "application/json")}
              >
                <DownloadSimple aria-hidden="true" />
                Download JSON
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => void copyJson()}>
                <Copy aria-hidden="true" />
                Copy JSON
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => save("catalog.csv", catalogCsv(records, fields), "text/csv")}
              >
                <FileCsv aria-hidden="true" />
                Download CSV
              </button>
              <span className={css.withHelp}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setDialog("expand")}
                >
                  <TreeStructure aria-hidden="true" />
                  Expand more
                </button>
                <HelpTip help="cr-expand" />
              </span>
              <span className={css.withHelp}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setDialog("reextract")}
                >
                  <ArrowsClockwise aria-hidden="true" />
                  Re-extract
                </button>
                <HelpTip help="cr-reextract" />
              </span>
            </div>
          </header>

          <div className={`seg ${css.views}`} role="radiogroup" aria-label="View">
            {(
              [
                ["table", "Table", Table],
                ["graph", "Graph", GraphIcon],
                ["json", "JSON", BracketsCurly],
              ] as const
            ).map(([value, label, Icon]) => (
              <label key={value} className={`seg-opt ${css.viewOpt}`}>
                <input
                  type="radio"
                  name="cr-view"
                  checked={view === value}
                  onChange={() => setView(value)}
                />
                <Icon aria-hidden="true" />
                {label}
              </label>
            ))}
          </div>

          {view === "table" && (
            <div className={css.tableLayout}>
              <div className={css.main}>
                {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls */}
                <div role="search" aria-label="Filter records" className={css.filters}>
                  <div className={css.search}>
                    <MagnifyingGlass aria-hidden="true" className={css.searchIcon} />
                    <input
                      className="input"
                      type="search"
                      aria-label="Search name, acronym or id"
                      placeholder="Search name, acronym, id"
                      value={filters.q}
                      onChange={(e) => setFilter({ q: e.target.value })}
                    />
                  </div>
                  {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls */}
                  <div role="group" aria-label="Type" className={css.chips}>
                    {types.map((t) => {
                      const on = filters.types.includes(t);
                      return (
                        <button
                          key={t}
                          type="button"
                          className={css.chip}
                          aria-pressed={on}
                          onClick={() =>
                            setFilter({
                              types: on
                                ? filters.types.filter((x) => x !== t)
                                : [...filters.types, t],
                            })
                          }
                        >
                          <span
                            aria-hidden="true"
                            className={css.typeDot}
                            style={{ background: color(t) }}
                          />
                          {t}
                          <span className={css.faint}>
                            {records.filter((r) => typeOf(r, fields) === t).length}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <button
                    type="button"
                    className={css.flagToggle}
                    aria-pressed={filters.flagged}
                    onClick={() => setFilter({ flagged: !filters.flagged })}
                  >
                    <Warning aria-hidden="true" />
                    Flagged only
                    <span className={css.faint}>
                      {records.filter((r) => flagsOf(r).length).length}
                    </span>
                  </button>
                  <label className={css.missing}>
                    Missing
                    <select
                      className="input"
                      value={filters.missing}
                      onChange={(e) => setFilter({ missing: e.target.value })}
                    >
                      <option value="">any field</option>
                      {fields
                        .filter((f) => f.type !== "slug" && f.type !== "enum" && f.name !== "name")
                        .map((f) => (
                          <option key={f.name} value={f.name}>
                            {f.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <span aria-live="polite" className={css.count}>
                    {shown.length === n ? `${n} records` : `${shown.length} of ${n}`}
                  </span>
                </div>
                <div className={css.tableWrap}>
                  <table className={css.table}>
                    <thead>
                      <tr>
                        {fields.map((f) => (
                          <th key={f.name} scope="col">
                            {f.name}
                          </th>
                        ))}
                        <th scope="col">flags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((r) => {
                        const id = idOf(r, fields);
                        const flags = flagsOf(r);
                        const open = () => setSelected(id);
                        return (
                          <tr
                            key={id}
                            tabIndex={0}
                            aria-label={`${nameOf(r, fields)}, ${typeOf(r, fields)}${flags.length ? `, ${flags.length} flags` : ""}`}
                            aria-selected={selected === id}
                            onClick={open}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                open();
                              }
                            }}
                          >
                            {fields.map((f) => (
                              <Cell key={f.name} record={r} field={f} fields={fields} byId={byId} />
                            ))}
                            <td>
                              {flags.length > 0 && (
                                <span
                                  className={css.flagBadge}
                                  title={`${flags.length} ${flags.length === 1 ? "flag" : "flags"}: ${flags.join("; ")}`}
                                >
                                  <Warning aria-hidden="true" />
                                  {flags.length}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!shown.length && (
                    <div className={css.empty}>
                      <FunnelX aria-hidden="true" />
                      No records match these filters.
                      <button
                        type="button"
                        className={`btn btn-ghost ${css.clear}`}
                        onClick={() => setFilters(NO_FILTERS)}
                      >
                        Clear filters
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <Summary
                catalog={catalog}
                records={records}
                fields={fields}
                onMissing={(field) => {
                  setFilters({ ...NO_FILTERS, missing: field });
                  setView("table");
                }}
              />
            </div>
          )}

          {view === "graph" && (
            <GraphView
              records={records}
              fields={fields}
              types={types}
              color={color}
              selected={selected}
              onOpen={setSelected}
            />
          )}

          {view === "json" && <JsonView records={records} />}
        </div>
      </div>
      {sel && (
        <Drawer
          record={sel}
          fields={fields}
          byId={byId}
          depth={depthOf.get(idOf(sel, fields)) ?? 0}
          phone={isPhone}
          onClose={() => setSelected(null)}
        />
      )}
      {dialog === "expand" && (
        <ExpandDialog detail={detail} structure={structure} onClose={() => setDialog(null)} />
      )}
      {dialog === "reextract" && (
        <ReextractDialog detail={detail} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}

type Field = ReturnType<typeof columnsOf>[number];

const MONO = new Set(["slug", "url", "date"]);
const WIDE: Record<string, string> = { url: "180px", text: "200px" };

function Cell(props: {
  record: CatalogRecord;
  field: Field;
  fields: Field[];
  byId: Map<string, CatalogRecord>;
}) {
  const { record, field, fields, byId } = props;
  const value = record[field.name];
  if (field.type === "enum")
    return (
      <td title={String(value ?? "")}>
        <span className={`tag tag-neutral ${css.typeChip}`}>{String(value ?? "")}</span>
      </td>
    );
  if (field.type === "ref") {
    const parent = value == null ? undefined : byId.get(String(value));
    return (
      <td
        className={css.cell}
        data-faint={!parent || undefined}
        style={{ maxWidth: 220 }}
        title={parent ? `${nameOf(parent, fields)} (${value})` : "seed · no parent"}
      >
        {parent ? nameOf(parent, fields) : "—"}
      </td>
    );
  }
  const name = field.name === nameOf(record, fields) || field.name === "name";
  const mono = MONO.has(field.type) || field.name === shortField(fields);
  return (
    <td
      className={css.cell}
      data-missing={value == null || undefined}
      data-mono={mono || undefined}
      data-id={field.type === "slug" || undefined}
      style={{ maxWidth: name ? 280 : (WIDE[field.type] ?? "none") }}
      title={value == null ? `${field.name} missing` : String(value)}
    >
      {value == null ? "—" : String(value)}
    </td>
  );
}

function Summary(props: {
  catalog: Catalog;
  records: CatalogRecord[];
  fields: Field[];
  onMissing: (field: string) => void;
}) {
  const { catalog, records, fields } = props;
  const depthRows = byDepth(records, fields);
  const most = Math.max(1, ...depthRows.map(([, c]) => c));
  const n = records.length;
  return (
    <aside aria-label="Summary" className={css.aside}>
      <h2 className={css.h2}>Summary</h2>
      <section className={css.sumSection}>
        <h3 className={css.h3}>Stop reason</h3>
        <span className={css.reason}>
          <CheckCircle aria-hidden="true" />
          {catalog.reason}
        </span>
        {catalog.note && <span className={css.note}>{catalog.note}</span>}
      </section>
      <section className={css.sumSection}>
        <h3 className={css.h3}>Nodes by depth</h3>
        <ul className={css.bars}>
          {depthRows.map(([d, c]) => (
            <li key={d} role="img" aria-label={`depth ${d}: ${c} nodes`} className={css.depthRow}>
              <span>depth {d}</span>
              <div className={css.track}>
                <div className={css.bar} style={{ width: `${Math.round((c / most) * 100)}%` }} />
              </div>
              <span className={css.num}>{c}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className={css.sumSection}>
        <h3 className={css.h3}>Least filled</h3>
        <ul className={css.worst}>
          {worstFilled(records, fields).map((w) => (
            <li key={w.field}>
              <div className={css.worstHead}>
                <span className={css.mono}>{w.field}</span>
                <span className={css.worstN}>
                  {w.filled}
                  <span className={css.faint}> / {n}</span>
                </span>
              </div>
              <div className={css.track}>
                <div
                  className={css.warnBar}
                  style={{ width: `${n ? Math.round((w.filled / n) * 100) : 0}%` }}
                />
              </div>
              <button
                type="button"
                className={`btn btn-ghost ${css.showMissing}`}
                aria-label={`Show records missing ${w.field}`}
                onClick={() => props.onMissing(w.field)}
              >
                Show missing
              </button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}

function GraphView(props: {
  records: CatalogRecord[];
  fields: Field[];
  types: string[];
  color: (type: string) => string;
  selected: string | null;
  onOpen: (id: string) => void;
}) {
  const { records, fields, types, color, selected, onOpen } = props;
  const g = graphLayout(records, fields);
  return (
    <div className={css.graphWrap}>
      {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled legend row */}
      <div role="group" aria-label="Legend" className={css.legend}>
        {types.map((t) => (
          <span key={t} className={css.legendItem}>
            <span aria-hidden="true" className={css.legendDot} style={{ background: color(t) }} />
            <span className={css.mono}>{t}</span>
          </span>
        ))}
        <span className={css.legendItem}>
          <span aria-hidden="true" className={css.legendRing} />
          flagged
        </span>
        <span className={css.legendHint}>Click a node to open it</span>
      </div>
      <div className={css.graphScroll}>
        <svg
          width={g.width}
          height={g.height}
          viewBox={`0 0 ${g.width} ${g.height}`}
          aria-label="Catalog graph by parent"
          className={css.svg}
        >
          {g.edges.map((e) => (
            <path key={`${e.from}-${e.to}`} d={e.d} className={css.edge} />
          ))}
          {g.nodes.map((node) => {
            const r = node.record;
            const label = graphLabel(r, fields);
            const flagged = flagsOf(r).length > 0;
            const key = (e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen(node.id);
              }
            };
            return (
              // biome-ignore lint/a11y/useSemanticElements: an SVG group cannot be a <button>
              <g
                key={node.id}
                transform={`translate(${node.x} ${node.y})`}
                role="button"
                tabIndex={0}
                aria-label={`${nameOf(r, fields)}, ${typeOf(r, fields)}${flagged ? ", flagged" : ""}`}
                className={css.gnode}
                onClick={() => onOpen(node.id)}
                onKeyDown={key}
              >
                <rect
                  x={-10}
                  y={-11}
                  width={28 + label.length * 7}
                  height={22}
                  rx={5}
                  className={css.hit}
                  data-selected={selected === node.id || undefined}
                />
                {flagged && <circle r={8.5} className={css.ring} />}
                <circle r={5} style={{ fill: color(typeOf(r, fields)) }} />
                <text x={14} y={4} className={css.label}>
                  {label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function JsonView({ records }: { records: CatalogRecord[] }) {
  const lines = recordsJson(records).split("\n");
  return (
    <div className={css.jsonWrap}>
      <span className={css.note}>
        {records.length} records · {lines.length} lines
      </span>
      {/* biome-ignore lint/a11y/noNoninteractiveTabindex: the region scrolls by keyboard */}
      <section aria-label="Catalog JSON" tabIndex={0} className={css.json}>
        {lines.map((line, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: lines are positional
          <div key={i} className={css.jsonLine}>
            <span aria-hidden="true" className={css.lineNo}>
              {i + 1}
            </span>
            <span className={css.lineText}>{line}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

function Drawer(props: {
  record: CatalogRecord;
  fields: Field[];
  byId: Map<string, CatalogRecord>;
  depth: number;
  phone: boolean;
  onClose: () => void;
}) {
  const { record, fields, byId, depth, onClose } = props;
  const { overlay } = useUi();
  useEffect(() => overlay("dialog", onClose), [overlay, onClose]);
  const name = nameOf(record, fields);
  const flags = flagsOf(record);
  const pages = pagesOf(record);
  return (
    <aside
      role="dialog"
      aria-label={name}
      className={css.drawer}
      data-phone={props.phone}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <header className={css.drawerHead}>
        <div className={css.drawerTitle}>
          <h2>{name}</h2>
          <span className={css.drawerMeta}>
            <span className={`tag tag-neutral ${css.typeChip}`}>{typeOf(record, fields)}</span>
            <span className={css.mono}>{idOf(record, fields)}</span>
            <span className={css.faint}>depth {depth}</span>
          </span>
        </div>
        <button
          type="button"
          className={`btn btn-ghost btn-icon ${css.close}`}
          aria-label="Close"
          // biome-ignore lint/a11y/noAutofocus: the drawer takes focus when it opens
          autoFocus
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
      </header>
      <div className={css.drawerBody}>
        {flags.length > 0 && (
          <div role="note" className={css.callout}>
            <Warning aria-hidden="true" />
            <ul>
              {flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
        )}
        <dl className={css.fields}>
          {fields.map((f) => {
            const value = record[f.name];
            const ref = f.type === "ref";
            const parent = ref && value != null ? byId.get(String(value)) : undefined;
            const text =
              value == null
                ? ref
                  ? "— seed, no parent"
                  : "— not found"
                : parent
                  ? `${nameOf(parent, fields)} · ${value}`
                  : String(value);
            const src =
              value == null || f.type === "slug" || f.type === "enum"
                ? ""
                : (record.sources?.[f.name] ?? "");
            return (
              <div key={f.name} className={css.field}>
                <dt>{f.name}</dt>
                <dd
                  data-missing={(value == null && !ref) || undefined}
                  data-muted={(value == null && ref) || undefined}
                >
                  {text}
                </dd>
                {src && (
                  <a href={src} target="_blank" rel="noreferrer" className={css.srcLink}>
                    <Link aria-hidden="true" />
                    {src.replace(/^https?:\/\/(www\.)?/, "")}
                  </a>
                )}
              </div>
            );
          })}
        </dl>
        <section className={css.sumSection}>
          <h3 className={css.h3}>
            Pages used <span className={css.pageN}>{pages.length}</span>
          </h3>
          <ol className={css.pages}>
            {pages.map((p) => (
              <li key={p.url}>
                <a href={p.url} target="_blank" rel="noreferrer">
                  {hostOf(p.url)}
                </a>
                <span className={css.pageUrl}>{p.url}</span>
                <span className={css.faint}>{p.fields.join(", ")}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </aside>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ExpandDialog(props: {
  detail: RunDetail;
  structure: Structure | null;
  onClose: () => void;
}) {
  const api = useApi();
  const { follow, toast } = useUi();
  const base = limitsOf(props.structure ?? props.detail.form?.structure);
  const [limits, setLimits] = useState(base);
  const [busy, setBusy] = useState(false);
  const valid = LIMITS.every((l) => limits[l.key] >= base[l.key] && limits[l.key] <= l.max);

  async function confirm() {
    setBusy(true);
    try {
      const created = await api.forkRun(props.detail.run_id, { from: "expand", limits });
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      toast((e as Error).message, { error: true });
      setBusy(false);
    }
  }

  return (
    <Dialog title="Expand more" onClose={props.onClose} className={css.dialog}>
      <p className={css.dialogNote}>
        Raises the limits and resumes from the frontier. Records already extracted are kept.
      </p>
      <div className={css.dialogLimits}>
        {LIMITS.map((l) => (
          <label key={l.key} className={css.dialogLimit}>
            {l.label}
            <input
              className="input"
              type="number"
              min={base[l.key]}
              max={l.max}
              value={Number.isNaN(limits[l.key]) ? "" : limits[l.key]}
              onChange={(e) =>
                setLimits({ ...limits, [l.key]: Number.parseInt(e.target.value, 10) })
              }
            />
          </label>
        ))}
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={props.onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !valid}
          onClick={() => void confirm()}
        >
          <TreeStructure aria-hidden="true" />
          Expand from the frontier
        </button>
      </div>
    </Dialog>
  );
}

function ReextractDialog({ detail, onClose }: { detail: RunDetail; onClose: () => void }) {
  const api = useApi();
  const { follow, toast } = useUi();
  const baseModel = detail.model ?? "";
  const baseEffort = detail.reasoning?.write ?? "default";
  const [model, setModel] = useState(baseModel);
  const [effort, setEffort] = useState(baseEffort);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    const llm: NonNullable<Parameters<typeof api.forkRun>[1]["llm"]> = {};
    if (model.trim() && model.trim() !== baseModel) llm.model = model.trim();
    if (effort !== baseEffort) llm.reasoning = { write: effort };
    try {
      const created = await api.forkRun(detail.run_id, {
        from: "extract",
        ...(Object.keys(llm).length ? { llm } : {}),
      });
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      toast((e as Error).message, { error: true });
      setBusy(false);
    }
  }

  return (
    <Dialog title="Re-extract" onClose={onClose} className={css.dialog}>
      <p className={css.dialogNote}>
        Runs extract and assemble again. The fetched pages are kept, so nothing is crawled again.
      </p>
      <div className={css.dialogLimits}>
        <label className={css.dialogLimit}>
          Model
          <input
            className={`input ${css.modelInput}`}
            value={model}
            spellCheck={false}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <label className={css.dialogLimit}>
          Thinking
          <select
            className="input"
            value={effort}
            onChange={(e) => setEffort(e.target.value as typeof effort)}
          >
            {EFFORTS.map((x) => (
              <option key={x} value={x}>
                {EFFORT_LABELS[x]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void confirm()}
        >
          <ArrowsClockwise aria-hidden="true" />
          Re-extract
        </button>
      </div>
    </Dialog>
  );
}
