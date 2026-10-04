// Settings: the profile and GPU policy lines, and provider cards with their last stored health check.
import {
  ArrowClockwise,
  CheckCircle,
  CircleDashed,
  CircleNotch,
  Cpu,
  Heartbeat,
  type Icon,
  MinusCircle,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import type { HealthReport, ProfileInfo, ProviderCheck } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { Seg } from "../../components/Seg";
import css from "./ProvidersSection.module.css";

const ROLES: Record<string, string> = {
  search: "Search",
  fetch: "Fetch",
  prefilter: "Prefilter",
  score: "Scorer",
  llm: "LLM",
};
/** The card title for a server block; an unknown block is capitalised. */
function roleTitle(c: ProviderCheck): string {
  if (c.role === "prefilter" && c.provider === "embeddings") return "Embeddings";
  return ROLES[c.role] ?? c.role.charAt(0).toUpperCase() + c.role.slice(1);
}
/** The blocks whose models share a GPU, which the GPU policy line names. */
const GPU_ROLES = new Set(["prefilter", "score", "llm"]);
const POLICIES = [
  { value: "shared", label: "Shared" },
  { value: "exclusive", label: "Exclusive" },
] as const;

export function policyText(report: HealthReport): string {
  const devices = [
    ...new Set(report.checks.flatMap((c) => (GPU_ROLES.has(c.role) && c.device ? [c.device] : []))),
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
export function healthWarns(report: HealthReport): boolean {
  return report.checks.some((c) => c.status === "degraded" || c.status === "down");
}

/** "just now" under 10 s, "N s ago" under a minute, else "N m ago". */
export function ago(at: string, now: number): string {
  const s = Math.max(0, Math.round((now - Date.parse(at)) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s} s ago`;
  return `${Math.round(s / 60)}m ago`;
}

/** The strip's status line and detail line for a stored check. */
export function healthLines(check: ProviderCheck, now: number): [string, string] {
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
  const [report, setReport] = useState<HealthReport | null>(null);
  const [checking, setChecking] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState("");
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [now, setNow] = useState(Date.now);

  const show = useCallback(
    (result: HealthReport) => {
      setReport(result);
      setNow(Date.now());
      setHealthWarn(healthWarns(result));
    },
    [setHealthWarn],
  );

  // Opening Settings only reads the stored results; a probe runs only when the user clicks Check.
  useEffect(() => {
    api.health().then(show, (e: Error) => setError(e.message));
    api.listProfiles().then(setProfiles, () => {});
  }, [api, show]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const check = async (roles: string[], blocks?: string[]) => {
    setChecking((current) => new Set([...current, ...roles]));
    setError("");
    try {
      show(await api.checkHealth(blocks, report?.profile));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking((current) => new Set([...current].filter((role) => !roles.includes(role))));
    }
  };
  const allRoles = (report?.checks ?? []).map((c) => c.role);
  const checkAll = () => check(allRoles);

  const profile = report?.profile ?? profiles.find((p) => p.active)?.name ?? "";
  const description = profiles.find((p) => p.name === profile)?.description;
  return (
    <>
      <div className={css.header}>
        <h1 className={page.h1}>Settings</h1>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={checkAll}
          disabled={!report || checking.size > 0}
        >
          <Heartbeat aria-hidden="true" />
          Check all providers
        </button>
      </div>
      <div className={css.lines}>
        <span className={css.profile}>
          <Cpu className={css.cpu} aria-hidden="true" />
          <span className={css.muted}>Active profile</span>
          <span className={css.profileName}>{profile}</span>
          <HelpTip help="profile" />
          {description && <span className={css.muted}>· {description}</span>}
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
            <span className={css.policyText}>{policyText(report)}</span>
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
      <div className={css.grid}>
        {(report?.checks ?? []).map((c) => (
          <Card
            key={c.role}
            check={c}
            checking={checking.has(c.role)}
            now={now}
            onCheck={() => check([c.role], [c.role])}
          />
        ))}
      </div>
    </>
  );
}

type CardProps = { check: ProviderCheck; checking: boolean; now: number; onCheck: () => void };

function Card({ check: c, checking, now, onCheck }: CardProps) {
  const state = checking ? "checking" : c.status;
  const Glyph = checking ? CircleNotch : (ICONS[c.status] ?? MinusCircle);
  const [text, detail] = checking ? ["Checking…", c.url] : healthLines(c, now);
  const mono = checking || c.status === "down";
  return (
    <section className={`card elev-sm ${css.card}`} aria-label={roleTitle(c)}>
      <div className={css.cardTop}>
        <span className="card-kicker">{roleTitle(c)}</span>
        <button
          type="button"
          className={`btn btn-ghost ${css.check}`}
          onClick={onCheck}
          disabled={checking}
          aria-label={`Check ${roleTitle(c)} provider`}
        >
          <ArrowClockwise className={checking ? css.spinFast : undefined} aria-hidden="true" />
          Check
        </button>
      </div>
      <div className={`card-title ${css.name}`}>{c.provider}</div>
      <dl className={css.dl}>
        <dt>Base URL</dt>
        <dd title={c.url}>{c.url || "–"}</dd>
        <dt>Model</dt>
        <dd title={c.model ?? undefined}>{c.model || "–"}</dd>
        <dt className={css.helpTerm}>
          Device
          <HelpTip help="pdevice" />
        </dt>
        <dd>{c.device || "–"}</dd>
        <dt className={css.helpTerm}>
          Unload
          <HelpTip help="unload" />
        </dt>
        <dd>{c.release ?? "none"}</dd>
      </dl>
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
