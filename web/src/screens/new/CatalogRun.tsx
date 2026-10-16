// The catalog form's "Run" group, shown as soon as Catalog is picked: the Profile row with its
// Advanced box (the research form's choice and edits) and the Questions row.
import type { ProfileInfo, QuestionsOptions } from "../../api/types";
import type { AskDraft } from "../../run/ask";
import { ProfileRow, type ProfileView } from "./OptionsPanel";
import { QuestionsRow } from "./QuestionsRow";
import { Row } from "./StructurePanel";
import css from "./StructurePanel.module.css";

type Props = {
  /** The profile choice and its Advanced edits, shared with the research form. */
  profile: ProfileView & {
    profiles: ProfileInfo[];
    name: string;
    words: number;
    onPick: (name: string) => void;
  };
  questions: { value: AskDraft; defaults: QuestionsOptions; onChange: (value: AskDraft) => void };
};

export function CatalogRun({ profile, questions }: Props) {
  return (
    <div className={css.panel}>
      <div className={css.head}>
        <span className={css.group}>Run</span>
      </div>
      <Row label="Profile" help="profile" id="c-profile-l" row="c-profile">
        <ProfileRow
          profiles={profile.profiles}
          profile={profile.name}
          view={profile}
          words={profile.words}
          rounds={1}
          kind="catalog"
          onPick={profile.onPick}
        />
      </Row>
      <QuestionsRow
        idPrefix="cq"
        value={questions.value}
        defaults={questions.defaults}
        onChange={questions.onChange}
      />
    </div>
  );
}
