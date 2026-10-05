import { useEffect, useState } from "react";
import type { ServerSettings } from "../../api/types";
import { useApi } from "../../app/context";
import page from "../../components/Page.module.css";
import { ProvidersSection } from "./ProvidersSection";
import { RunDefaults } from "./RunDefaults";
import { SecuritySection } from "./SecuritySection";
import css from "./SettingsScreen.module.css";
import { WritingDefaults } from "./WritingDefaults";

export function SettingsScreen() {
  const api = useApi();
  const [settings, setSettings] = useState<ServerSettings | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings, () => {});
  }, [api]);

  return (
    <div className={page.page}>
      <div className={`${page.inner} ${css.inner}`}>
        <ProvidersSection />
        <RunDefaults settings={settings} setSettings={setSettings} />
        <WritingDefaults settings={settings} setSettings={setSettings} />
        <SecuritySection />
      </div>
    </div>
  );
}
