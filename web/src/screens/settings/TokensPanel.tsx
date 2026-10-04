// Settings: API tokens with a one-time reveal and a confirmed revoke.
import { Check, Copy, EyeSlash, Key, Plus, Trash } from "@phosphor-icons/react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import type { TokenCreated, TokenInfo } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { Dialog } from "../../components/Dialog";
import { HelpTip } from "../../components/HelpTip";
import { dateTime, shortDate } from "../../format";
import css from "./SecuritySection.module.css";

export function Tokens() {
  const api = useApi();
  const { toast } = useUi();
  const [tokens, setTokens] = useState<TokenInfo[] | null>(null);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<TokenCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<TokenInfo | null>(null);

  const load = useCallback(() => api.listTokens().then(setTokens, () => {}), [api]);
  useEffect(() => {
    void load();
  }, [load]);
  const closeRevoke = useCallback(() => setRevoking(null), []);

  async function create(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const token = await api.createToken(trimmed);
    setName("");
    setCopied(false);
    setCreated(token);
    await load();
  }

  async function revoke(token: TokenInfo) {
    setRevoking(null);
    await api.deleteToken(token.id);
    setTokens((ts) => ts?.filter((t) => t.id !== token.id) ?? null);
    if (created?.id === token.id) setCreated(null);
    toast(`Token “${token.name}” revoked`);
  }

  return (
    <>
      <div className={css.stack}>
        <div className={`${css.strong} ${css.titleRow}`}>
          API tokens
          <HelpTip help="apitokens" />
        </div>
        <div className={css.muted}>
          For the CLI and scripts that call the local API, sent as{" "}
          <span className={css.code}>Authorization: Bearer &lt;token&gt;</span>.
        </div>
      </div>
      <form className={css.create} onSubmit={create}>
        <input
          className="input"
          aria-label="Token name"
          placeholder="Token name, e.g. ci-runner"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={!name.trim()}>
          <Plus aria-hidden="true" />
          Create token
        </button>
      </form>
      {created && (
        <div role="status" className={css.reveal}>
          <div className={css.revealHead}>
            <Key className={css.key} aria-hidden="true" />
            Token “{created.name}” created
          </div>
          <div className={css.row}>
            <code className={css.token}>{created.token}</code>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                navigator.clipboard?.writeText(created.token).catch(() => {});
                setCopied(true);
              }}
            >
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className={css.warnRow}>
            <EyeSlash className={css.eye} aria-hidden="true" />
            <span>Copy it now. It won't be shown again.</span>
            <button
              type="button"
              className={`btn btn-ghost ${css.done}`}
              onClick={() => setCreated(null)}
            >
              Done
            </button>
          </div>
        </div>
      )}
      {tokens?.length === 0 && (
        <div className={css.empty}>
          No tokens. The local API only accepts requests from a signed-in browser.
        </div>
      )}
      {!!tokens?.length && (
        <div className={css.scroll}>
          <table className={`table ${css.table}`}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Token</th>
                <th>Created</th>
                <th>Last used</th>
                <th className={css.right}>
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className={css.masked}>{t.masked}</td>
                  <td className={css.date}>{shortDate(t.created)}</td>
                  <td className={css.date}>{t.last_used ? dateTime(t.last_used) : "Never"}</td>
                  <td className={css.right}>
                    <button
                      type="button"
                      className={`btn btn-ghost ${css.revoke}`}
                      onClick={() => setRevoking(t)}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {revoking && (
        <Dialog role="alertdialog" title={`Revoke “${revoking.name}”?`} onClose={closeRevoke}>
          <div className="dialog-body">
            Anything using this token stops working immediately. This can't be undone.
          </div>
          <div className="dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={closeRevoke}>
              Cancel
            </button>
            <button
              type="button"
              className={`btn btn-secondary ${css.danger}`}
              onClick={() => revoke(revoking)}
            >
              <Trash aria-hidden="true" />
              Revoke token
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
