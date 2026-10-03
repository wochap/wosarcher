// The sign-in overlay over the current screen: idle, wrong password, or paused.
import {
  Eye,
  EyeSlash,
  FunnelSimple,
  LockSimple,
  SignIn,
  Timer,
  WarningCircle,
} from "@phosphor-icons/react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useApi } from "../../app/context";
import { minSec } from "../../format";
import css from "./LoginScreen.module.css";

export type LoginState =
  | { kind: "idle" }
  | { kind: "wrong"; attemptsLeft: number }
  | { kind: "limited"; until: number; total: number };

type Props = { initial?: LoginState; onSignedIn: () => void };

export function LoginScreen({ initial = { kind: "idle" }, onSignedIn }: Props) {
  const api = useApi();
  const [state, setState] = useState<LoginState>(initial);
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [now, setNow] = useState(Date.now);
  const field = useRef<HTMLInputElement>(null);

  const limited = state.kind === "limited";
  const remaining = limited ? Math.max(0, Math.ceil((state.until - now) / 1000)) : 0;

  useEffect(() => {
    if (!limited) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [limited]);

  useEffect(() => {
    if (limited && remaining === 0) setState({ kind: "idle" });
  }, [limited, remaining]);

  useEffect(() => {
    if (state.kind !== "limited") field.current?.focus();
  }, [state]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (limited || !password) return;
    const result = await api.login(password);
    setPassword("");
    if (result.kind === "ok") onSignedIn();
    else if (result.kind === "wrong")
      setState({ kind: "wrong", attemptsLeft: result.attemptsLeft });
    else {
      const start = Date.now();
      setNow(start);
      setState({
        kind: "limited",
        until: start + result.retryAfter * 1000,
        total: result.retryAfter,
      });
    }
  }

  const left = state.kind === "wrong" ? state.attemptsLeft : 0;
  return (
    <div className={css.overlay}>
      <form className={css.form} onSubmit={submit}>
        <div className={css.brand}>
          <FunnelSimple className={css.brandIcon} aria-hidden="true" />
          <span className={css.brandName}>wosarcher</span>
        </div>
        <div>
          <h1 className={css.title}>Sign in</h1>
          <p className={css.lead}>Enter the password for this wosarcher instance.</p>
        </div>
        <div className={`field ${css.field}`}>
          <label htmlFor="pw">Password</label>
          <div className={css.wrap}>
            <input
              id="pw"
              ref={field}
              className={`input ${css.input}`}
              type={shown ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={limited}
              aria-invalid={state.kind === "wrong"}
              aria-describedby="pw-msg"
            />
            <button
              type="button"
              className={css.reveal}
              onClick={() => setShown((s) => !s)}
              aria-label={shown ? "Hide password" : "Show password"}
            >
              {shown ? <EyeSlash aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </button>
          </div>
        </div>
        {state.kind === "wrong" && (
          <div id="pw-msg" role="alert" className={css.alert} data-tone="danger">
            <div className={css.alertRow}>
              <WarningCircle className={css.alertIcon} aria-hidden="true" />
              <div>
                <div className={css.alertTitle}>Wrong password</div>
                <div className={css.alertText}>
                  {left} attempt{left === 1 ? "" : "s"} left before sign-in pauses.
                </div>
              </div>
            </div>
          </div>
        )}
        {state.kind === "limited" && (
          <div id="pw-msg" role="alert" className={css.alert} data-tone="warn">
            <div className={css.alertRow}>
              <Timer className={css.alertIcon} aria-hidden="true" />
              <div>
                <div className={css.alertTitle}>Too many attempts</div>
                <div className={css.alertText}>
                  Sign-in is paused. Try again in {minSec(remaining)}.
                </div>
              </div>
            </div>
            <div className={css.track}>
              <div
                className={css.bar}
                style={{ width: `${Math.round((remaining / state.total) * 100)}%` }}
              />
            </div>
          </div>
        )}
        <button
          className={`btn btn-primary ${css.submit}`}
          type="submit"
          disabled={limited || !password}
        >
          {limited ? <LockSimple aria-hidden="true" /> : <SignIn aria-hidden="true" />}
          {limited ? `Try again in ${remaining} s` : "Sign in"}
        </button>
        <div className={css.host}>{window.location.host}</div>
      </form>
    </div>
  );
}
