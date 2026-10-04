// Settings: the profile and GPU policy lines, and provider cards with their last health result.
import {
  ArrowClockwise,
  CheckCircle,
  CircleDashed,
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
};
const HEALTHY = new Set(["ok", "skipped"]);
const ms = (n: number | null | undefined) => `${Math.round(n ?? 0).toLocaleString("en-US")} ms`;

export function healthText(check: ProviderCheck): string {
  const detail = check.detail ? ` · ${check.detail}` : "";
  switch (check.status) {
    case "ok":
      return `Healthy · ${ms(check.latency_ms)}`;
    case "degraded":
      return `Slow · ${ms(check.latency_ms)}${detail}`;
    case "down":
      return `Unreachable${detail}`;
    default:
      return `Skipped${detail}`;
  }
}

function ago(at: number, now: number): string {
  const s = Math.max(0, Math.round((now - at) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s} s ago`;
  return `${Math.round(s / 60)} min ago`;
}

export function ProvidersSection() {
  const api = useApi();
  const { setHealthWarn } = useUi();
  const [report, setReport] = useState<HealthReport | null>(null);
  const [checkedAt, setCheckedAt] = useState(0);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [now, setNow] = useState(Date.now);

  // The server checks every provider of the profile at once: one request serves every card.
  const check = useCallback(async () => {
    setChecking(true);
    setError("");
    try {
      const result = await api.health();
      setReport(result);
      setCheckedAt(Date.now());
      setNow(Date.now());
      setHealthWarn(result.checks.some((c) => !HEALTHY.has(c.status)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  }, [api, setHealthWarn]);

  useEffect(() => {
    void check();
    api.listProfiles().then(setProfiles, () => {});
  }, [api, check]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const profile = report?.profile ?? profiles.find((p) => p.active)?.name ?? "";
  const description = profiles.find((p) => p.name === profile)?.description;
  return (
    <>
      <div className={css.header}>
        <h1 className={page.h1}>Settings</h1>
        <button type="button" className="btn btn-secondary" onClick={check} disabled={checking}>
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
      <h2 className={`${page.section} ${css.providersTitle}`}>Providers</h2>
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
            checking={checking}
            ago={ago(checkedAt, now)}
            onCheck={check}
          />
        ))}
      </div>
    </>
  );
}

type CardProps = { check: ProviderCheck; checking: boolean; ago: string; onCheck: () => void };

function Card({ check: c, checking, ago: when, onCheck }: CardProps) {
  const state = checking ? "checking" : c.status;
  const Glyph = checking ? CircleDashed : (ICONS[c.status] ?? MinusCircle);
  return (
    <section className={`card elev-sm ${css.card}`} aria-label={roleTitle(c)}>
      <div className={css.cardTop}>
        <span className="card-kicker">{roleTitle(c)}</span>
        <button
          type="button"
          className={`btn btn-ghost ${css.check}`}
          onClick={onCheck}
          disabled={checking}
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
        <Glyph weight="fill" className={css.healthIcon} aria-hidden="true" />
        <span className={css.healthText}>
          {checking ? "Checking…" : healthText(c)}
          <HelpTip help="health" />
        </span>
        <span className={css.ago}>{checking ? "" : when}</span>
      </div>
    </section>
  );
}
