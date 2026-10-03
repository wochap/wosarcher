// Below 720px: one Live run panel at a time, picked by these tabs with their counts.
import type { LiveTab } from "../../app/context";
import css from "./PhoneTabs.module.css";

const TABS: { id: LiveTab; label: string }[] = [
  { id: "progress", label: "Progress" },
  { id: "sources", label: "Sources" },
  { id: "passages", label: "Passages" },
  { id: "report", label: "Report" },
];

type Props = {
  tab: LiveTab;
  onTab: (tab: LiveTab) => void;
  counts: Partial<Record<LiveTab, string>>;
};

export function PhoneTabs({ tab, onTab, counts }: Props) {
  return (
    <div role="tablist" className={css.tabs}>
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={tab === t.id}
          className={css.tab}
          onClick={() => onTab(t.id)}
        >
          {t.label}
          <span className={css.count}>{counts[t.id] ?? ""}</span>
        </button>
      ))}
    </div>
  );
}
