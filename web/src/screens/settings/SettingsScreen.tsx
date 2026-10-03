import page from "../../components/Page.module.css";
import { ProvidersSection } from "./ProvidersSection";
import { SecuritySection } from "./SecuritySection";
import css from "./SettingsScreen.module.css";
import { WritingDefaults } from "./WritingDefaults";

export function SettingsScreen() {
  return (
    <div className={page.page}>
      <div className={`${page.inner} ${css.inner}`}>
        <ProvidersSection />
        <WritingDefaults />
        <SecuritySection />
      </div>
    </div>
  );
}
