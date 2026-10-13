// Settings: the default profile and GPU policy lines, and the provider entries by block, each
// card with its last stored health check.
import {
  ArrowClockwise,
  CheckCircle,
  CircleDashed,
  CircleNotch,
  Heartbeat,
  type Icon,
  MinusCircle,
  Stack,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import type {
  Block,
  ModelInfo,
  ProfileInfo,
  ProviderEntry,
  ProvidersReport,
} from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { Seg } from "../../components/Seg";
import { Tag } from "../../components/Tag";
import { fmtN } from "../../run/depth";
import { BLOCK_LABELS, BLOCKS, entriesOf } from "../../run/profileValues";
import css from "./ProvidersSection.module.css";

/** The blocks whose models share a GPU, which the GPU policy line names. */
const GPU_BLOCKS: Block[] = ["prefilter", "score", "llm"];
const POLICIES = [
  { value: "shared", label: "Shared" },
  { value: "exclusive", label: "Exclusive" },
] as const;
const BLOCK_HELP: Record<Block, string> = {
  search: "p-search",
  fetch: "p-fetch",
  prefilter: "p-prefilter",
  score: "p-scorer",
  llm: "p-llm",
};

/** The `<block>/<name>` key a check names an entry by. */
const keyOf = (e: ProviderEntry) => `${e.block}/${e.name}`;

/** The default profile's entry per block that the report lists. */
function profileEntries(report: ProvidersReport, profile: ProfileInfo | undefined) {
  return BLOCKS.flatMap((b) => {
    const entry = report.entries.find((e) => e.block === b && e.name === profile?.use?.[b]);
    return entry ? [entry] : [];
  });
}

/** The policy sentence, naming the devices of the default profile's GPU entries. */
export function policyText(report: ProvidersReport, profile: ProfileInfo | undefined): string {
  const devices = [
    ...new Set(
      profileEntries(report, profile).flatMap((e) =>
        GPU_BLOCKS.includes(e.block) && e.device ? [e.device] : [],
      ),
    ),
  ];
  const on = devices.length ? ` on ${devices.join(", ")}` : "";
  return report.gpu_policy === "exclusive"
    ? `Each model unloads before the next one loads${on}.`
    : `All models stay loaded${on}.`;
}
const ICONS: Record<string, Icon> = {
  ok: CheckCircle,
  degraded: WarningCircle,
  down: XCircle,
  skipped: MinusCircle,
  unchecked: CircleDashed,
};
const SLOW_MS = 1000;
const ms = (n: number | null | undefined) => `${Math.round(n ?? 0).toLocaleString("en-US")} ms`;

/** True when the report has a slow or down provider: the sidebar's warn dot. */
export function healthWarns(report: ProvidersReport): boolean {
  return report.entries.some((e) => e.status === "degraded" || e.status === "down");
}

/** "just now" under 10 s, "N s ago" under a minute, else "N m ago". */
export function ago(at: string, now: number): string {
  const s = Math.max(0, Math.round((now - Date.parse(at)) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s} s ago`;
  return `${Math.round(s / 60)}m ago`;
}

/** The strip's status line and detail line for a stored check. */
export function healthLines(check: ProviderEntry, now: number): [string, string] {
  const when = check.checked_at ? `checked ${ago(check.checked_at, now)}` : "";
  switch (check.status) {
    case "ok":
      return [`OK · ${when}`, ms(check.latency_ms)];
    case "degraded": {
      const slow = (check.latency_ms ?? 0) > SLOW_MS;
      return [
        `Slow · ${when}`,
        slow ? `${ms(check.latency_ms)}, limit 1,000 ms` : (check.detail ?? ""),
      ];
    }
    case "down":
      return [`Down · ${when}`, check.detail ?? ""];
    case "skipped":
      return [check.detail ? `Skipped · ${check.detail}` : "Skipped", ""];
    default:
      return ["Not checked yet", ""];
  }
}

export function ProvidersSection() {
  const api = useApi();
  const { setHealthWarn } = useUi();
  const [report, setReport] = useState<ProvidersReport | null>(null);
  /** The entries being checked, by key; `all` while Check all runs. */
  const [checking, setChecking] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState("");
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [now, setNow] = useState(Date.now);

  const show = useCallback(
    (result: ProvidersReport) => {
      setReport(result);
      setNow(Date.now());
      setHealthWarn(healthWarns(result));
    },
    [setHealthWarn],
  );

  // Opening Settings only reads the stored results; a probe runs only when the user clicks Check.
  useEffect(() => {
    api.listProviders().then(show, (e: Error) => setError(e.message));
    api.listProfiles().then(setProfiles, () => {});
  }, [api, show]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  /** Checks one entry by key, or every entry with `all`. */
  const check = async (key: string) => {
    setChecking((current) => new Set([...current, key]));
    setError("");
    try {
      show(await api.checkProviders(key === ALL ? undefined : [key]));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking((current) => new Set([...current].filter((k) => k !== key)));
    }
  };

  const name = report?.profile ?? profiles.find((p) => p.active)?.name ?? "";
  const profile = profiles.find((p) => p.name === name);
  const used = profile?.use
    ? BLOCKS.flatMap((b) => (profile.use?.[b] ? [profile.use[b]] : [])).join(" · ")
    : "";
  return (
    <>
      <div className={css.header}>
        <h1 className={page.h1}>Settings</h1>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => void check(ALL)}
          disabled={!report || checking.has(ALL)}
        >
          <Heartbeat aria-hidden="true" />
          Check all providers
        </button>
      </div>
      <div className={css.lines}>
        <span className={css.profile}>
          <Stack className={css.stack} aria-hidden="true" />
          <span className={css.muted}>Default profile</span>
          <span className={css.profileName}>{name}</span>
          {used && <span className={css.profileEntries}>{used}</span>}
          <HelpTip help="profile" />
        </span>
        {report && (
          <span className={css.policy}>
            <span className={css.policyLabel}>
              GPU policy
              <HelpTip help="gpupolicy" />
            </span>
            <div className={css.policySeg}>
              <Seg
                label="GPU policy"
                name="gpu-policy"
                value={report.gpu_policy ?? "shared"}
                options={[...POLICIES]}
                onChange={() => {}}
                disabled
              />
            </div>
            <span className={css.policyText}>{policyText(report, profile)}</span>
          </span>
        )}
      </div>
      <div className={css.providersTitle}>
        <h2 className={page.section}>Providers</h2>
        <span className={css.note}>
          Checked only when you click, so idle GPU servers stay asleep.
        </span>
      </div>
      {error && (
        <div role="alert" className={css.error}>
          {error}
        </div>
      )}
      {report && (
        <div className={css.blocks}>
          {BLOCKS.map((block) => (
            <fieldset key={block} aria-labelledby={`pb-${block}`} className={css.block}>
              <div className={css.blockHead}>
                <h3 id={`pb-${block}`} className={css.blockTitle}>
                  {BLOCK_LABELS[block]}
                </h3>
                <HelpTip help={BLOCK_HELP[block]} label={BLOCK_LABELS[block]} />
              </div>
              <div className={css.grid}>
                {entriesOf(report.entries, block).map((e) =>
                  e.source === "builtin" ? (
                    <BuiltinCard key={e.name} entry={e} />
                  ) : (
                    <Card
                      key={e.name}
                      entry={e}
                      checking={checking.has(ALL) || checking.has(keyOf(e))}
                      busy={checking.has(ALL)}
                      now={now}
                      onCheck={() => void check(keyOf(e))}
                    />
                  ),
                )}
              </div>
            </fieldset>
          ))}
        </div>
      )}
    </>
  );
}

const ALL = "all";

function BuiltinCard({ entry }: { entry: ProviderEntry }) {
  return (
    <section className={`card ${css.builtin}`} aria-label={`${entry.name} (${entry.block})`}>
      <span className="card-kicker">{entry.provider || entry.name}</span>
      <div className={`card-title ${css.builtinName}`}>{entry.name}</div>
      <span className={css.note}>Built in, nothing to check.</span>
    </section>
  );
}

type CardProps = {
  entry: ProviderEntry;
  checking: boolean;
  /** Check all runs: every Check button is disabled. */
  busy: boolean;
  now: number;
  onCheck: () => void;
};

function Card({ entry: e, checking, busy, now, onCheck }: CardProps) {
  const status = e.status ?? "unchecked";
  const state = checking ? "checking" : status;
  const Glyph = checking ? CircleNotch : (ICONS[status] ?? MinusCircle);
  const [text, detail] = checking ? ["Checking…", e.url ?? ""] : healthLines(e, now);
  const mono = checking || status === "down";
  const llm = e.block === "llm";
  return (
    <section className={`card elev-sm ${css.card}`} aria-label={`${e.name} (${e.block})`}>
      <div className={css.cardTop}>
        <span className="card-kicker">{e.provider}</span>
        <button
          type="button"
          className={`btn btn-secondary ${css.check}`}
          onClick={onCheck}
          disabled={checking || busy}
          aria-label={`Check ${e.name} (${e.block})`}
        >
          <ArrowClockwise className={checking ? css.spinFast : undefined} aria-hidden="true" />
          Check
        </button>
      </div>
      <div className={`card-title ${css.name}`}>{e.name}</div>
      {e.error ? (
        <div role="alert" className={css.entryError}>
          {e.error}
        </div>
      ) : (
        <>
          <dl className={css.dl}>
            <dt>Base URL</dt>
            <dd title={e.url}>{e.url || "–"}</dd>
            {!llm && (
              <>
                <dt>Model</dt>
                <dd title={e.model}>{e.model || "–"}</dd>
              </>
            )}
            <dt className={css.helpTerm}>
              Device
              <HelpTip help="pdevice" />
            </dt>
            <dd>{e.device || "–"}</dd>
            <dt className={css.helpTerm}>
              Unload
              <HelpTip help="unload" />
            </dt>
            <dd>{e.release ?? "none"}</dd>
          </dl>
          {llm && <ModelList models={e.models ?? []} />}
        </>
      )}
      <div role="status" className={css.health} data-state={state}>
        <div className={css.healthLine}>
          <Glyph weight="fill" className={css.healthIcon} aria-hidden="true" />
          <span className={css.healthText}>
            {text}
            <HelpTip help="health" />
          </span>
        </div>
        {detail && <div className={mono ? `${css.detail} ${css.mono}` : css.detail}>{detail}</div>}
      </div>
    </section>
  );
}

/** An llm entry's models, the default first: "<window> window · <out> out" or fallback limits. */
function ModelList({ models }: { models: ModelInfo[] }) {
  return (
    <div className={css.models}>
      <span className={css.muted}>Models</span>
      <ul className={css.modelList}>
        {models.map((m, i) => (
          <li key={m.id}>
            <span className={css.modelId}>{m.id}</span>
            {i === 0 && (
              <Tag variant="accent" small>
                default
              </Tag>
            )}
            {m.context_window && m.max_output_tokens ? (
              <span className={css.limits}>
                {`${fmtN(m.context_window)} window · ${fmtN(m.max_output_tokens)} out`}
              </span>
            ) : (
              <span className={`${css.limits} ${css.faint}`}>fallback limits</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
