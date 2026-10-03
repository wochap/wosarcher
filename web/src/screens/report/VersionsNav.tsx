// The runs of one lineage, oldest first; pressing one shows its report.
import { GitBranch, MagnifyingGlass } from "@phosphor-icons/react";
import { go } from "../../app/route";
import type { Version } from "../../run/lineage";
import css from "./ReportScreen.module.css";

export function VersionsNav({ versions }: { versions: Version[] }) {
  if (versions.length < 2) return null;
  return (
    <nav aria-label="Report versions" className={css.versions}>
      <span className={css.kicker}>Versions</span>
      <div className={css.versionList}>
        {versions.map((v) => {
          const Glyph = v.run.parent_run_id ? GitBranch : MagnifyingGlass;
          return (
            <button
              key={v.run.run_id}
              type="button"
              className={css.version}
              aria-current={v.current ? "true" : undefined}
              onClick={() => go({ screen: "report", runId: v.run.run_id })}
            >
              <span className={css.versionHead}>
                <Glyph className={css.versionIcon} aria-hidden="true" />v{v.run.version ?? 1} ·{" "}
                {v.kind}
                <span className={css.versionId}>{v.run.run_id}</span>
              </span>
              <span className={css.versionDesc}>{v.description}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
