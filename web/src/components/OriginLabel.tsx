// Where a run was started, for runs not started in the browser: `cli`, or `api · <token>`.
import { Key, TerminalWindow } from "@phosphor-icons/react";
import type { Origin } from "../api/types";
import css from "./OriginLabel.module.css";

type Props = { origin?: Origin; tokenName?: string | null };

export function OriginLabel({ origin, tokenName }: Props) {
  if (origin === "cli") {
    return (
      <span className={css.label} title="Started from the wosarcher CLI on this machine">
        <TerminalWindow className={css.icon} aria-hidden="true" />
        cli
      </span>
    );
  }
  if (origin === "api") {
    return (
      <span className={css.label} title={`Started through the API with token “${tokenName ?? ""}”`}>
        <Key className={css.icon} aria-hidden="true" />
        api · {tokenName}
      </span>
    );
  }
  return null;
}
