// Settings: the browser session, sign out, and the API tokens panel.
import { SignOut } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { SessionInfo } from "../../api/types";
import { useApi, useAuth } from "../../app/context";
import page from "../../components/Page.module.css";
import { dateTime } from "../../format";
import css from "./SecuritySection.module.css";
import { Tokens } from "./TokensPanel";

export function SecuritySection() {
  const api = useApi();
  const [session, setSession] = useState<SessionInfo | null>(null);
  useEffect(() => {
    api.getSession().then(setSession, () => {});
  }, [api]);

  return (
    <>
      <h2 className={`${page.section} ${css.title}`}>Security</h2>
      <div className={`${page.panel} ${css.panel}`}>
        {session && <Session session={session} />}
        <div className={css.rule} />
        <Tokens />
      </div>
    </>
  );
}

function Session({ session }: { session: SessionInfo }) {
  const api = useApi();
  const { lock } = useAuth();
  let text = "No password is set; the server accepts local connections only.";
  if (session.method === "cookie" && session.since) {
    text = `Signed in on this browser since ${dateTime(session.since)}.`;
  } else if (session.method === "token") {
    text = `Signed in with the API token “${session.token_name ?? ""}”.`;
  }
  return (
    <div className={css.row}>
      <div className={css.grow}>
        <div className={css.strong}>Session</div>
        <div className={css.muted}>{text}</div>
      </div>
      {session.method === "cookie" && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={async () => {
            await api.logout();
            lock();
          }}
        >
          <SignOut aria-hidden="true" />
          Sign out
        </button>
      )}
    </div>
  );
}
