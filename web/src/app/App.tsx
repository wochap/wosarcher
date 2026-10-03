// The app: session check, the three contexts, the followed run, and the screen switch.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ApiClient, httpApi } from "../api/client";
import type { SocketFactory } from "../api/events";
import type { RunSummary } from "../api/types";
import { Toast, UNDO_MS, useToastState } from "../components/Toast";
import { useRun } from "../run/useRun";
import { HistoryScreen } from "../screens/history/HistoryScreen";
import { LiveScreen } from "../screens/live/LiveScreen";
import { LoginScreen, type LoginState } from "../screens/login/LoginScreen";
import { NewRunScreen } from "../screens/new/NewRunScreen";
import { ReportScreen } from "../screens/report/ReportScreen";
import { SettingsScreen } from "../screens/settings/SettingsScreen";
import {
  ApiContext,
  type Auth,
  AuthContext,
  type OverlayKind,
  type Ui,
  UiContext,
} from "./context";
import { type Overlay, useKeys } from "./keys";
import { go, type Route, type Screen, useRoute } from "./route";
import { Shell, useIsPhone } from "./Shell";
import { useTheme } from "./theme";

type Props = {
  /** Builds the client; `onUnauthorized` locks the app. Defaults to the HTTP client. */
  makeApi?: (onUnauthorized: () => void) => ApiClient;
  Socket?: SocketFactory;
  /** Dev preview: the sign-in state to start in. */
  login?: LoginState;
};

const ACTIVE = new Set(["queued", "running"]);

/** The newest queued or running run, which "Live run" follows at start. */
export function newestActive(runs: RunSummary[]): string | null {
  const active = runs.filter((r) => ACTIVE.has(r.status));
  active.sort((a, b) => b.created.localeCompare(a.created));
  return active[0]?.run_id ?? null;
}

function useOverlays() {
  const open = useRef<Overlay[]>([]);
  const overlay = useCallback((kind: OverlayKind, close: () => void) => {
    const entry = { kind, close };
    open.current = [...open.current, entry];
    return () => {
      open.current = open.current.filter((o) => o !== entry);
    };
  }, []);
  return { open, overlay };
}

export function App({ makeApi = httpApi, Socket, login }: Props) {
  const route = useRoute();
  const [theme, toggleTheme] = useTheme();
  const isPhone = useIsPhone();
  const { shown, toast, dismiss } = useToastState();
  const { open: overlays, overlay } = useOverlays();

  const [ready, setReady] = useState(false);
  const [locked, setLocked] = useState(false);
  const [method, setMethod] = useState<Auth["method"]>(null);
  const [epoch, setEpoch] = useState(0);
  const methodRef = useRef(method);
  methodRef.current = method;
  const lock = useCallback(() => {
    if (methodRef.current !== "none") setLocked(true);
  }, []);
  const unlock = useCallback(() => {
    setLocked(false);
    setEpoch((n) => n + 1);
  }, []);
  const api = useMemo(() => makeApi(lock), [makeApi, lock]);

  const [followed, follow] = useState<string | null>(null);
  const [healthWarn, setHealthWarn] = useState(false);
  const services = useMemo(() => ({ api, Socket }), [api, Socket]);
  const { view } = useRun(followed, services);
  const [hiddenRuns, setHidden] = useState<ReadonlySet<string>>(new Set());
  const unhide = useCallback((id: string) => {
    setHidden((h) => new Set([...h].filter((x) => x !== id)));
  }, []);
  // The delete timer lives here, so leaving History does not cancel it.
  const deleteRun = useCallback(
    (id: string) => {
      setHidden((h) => new Set(h).add(id));
      const timer = setTimeout(() => {
        api.deleteRun(id).catch((error: Error) => {
          unhide(id);
          toast(error.message);
        });
      }, UNDO_MS);
      toast("Run deleted", {
        undo: () => {
          clearTimeout(timer);
          unhide(id);
        },
      });
    },
    [api, toast, unhide],
  );

  useEffect(() => {
    if (login) setLocked(true);
    api.getSession().then(
      (session) => {
        setMethod(session.method);
        if (session.method === "none") setLocked(false);
        setReady(true);
        api.listRuns().then(
          (runs) => follow((f) => f ?? newestActive(runs)),
          () => {},
        );
      },
      () => setReady(true),
    );
  }, [api, login]);

  useEffect(() => {
    if (route.screen === "live" && route.runId) follow(route.runId);
  }, [route]);

  const goTo = useCallback(
    (screen: Screen) => {
      overlays.current = [];
      go(screen === "live" && followed ? { screen, runId: followed } : { screen });
    },
    [followed, overlays],
  );
  const screen: Screen = route.screen === "preview" ? "new" : route.screen;
  useKeys({ locked, screen, goTo, overlays: () => overlays.current });

  const ui: Ui = useMemo(
    () => ({
      theme,
      toggleTheme,
      isPhone,
      toast,
      overlay,
      followed,
      follow,
      healthWarn,
      setHealthWarn,
      hiddenRuns,
      deleteRun,
    }),
    [theme, toggleTheme, isPhone, toast, overlay, followed, healthWarn, hiddenRuns, deleteRun],
  );
  const auth: Auth = useMemo(
    () => ({ locked, method, lock, unlock }),
    [locked, method, lock, unlock],
  );
  const liveDot = !!view && ACTIVE.has(view.status);

  return (
    <ApiContext.Provider value={services}>
      <AuthContext.Provider value={auth}>
        <UiContext.Provider value={ui}>
          <Shell
            screen={screen}
            liveDot={liveDot}
            onGo={goTo}
            overlays={
              <>
                <Toast shown={shown} dismiss={dismiss} />
                {locked && <LoginScreen initial={login} onSignedIn={unlock} />}
              </>
            }
          >
            {ready && <Current key={epoch} route={route} />}
          </Shell>
        </UiContext.Provider>
      </AuthContext.Provider>
    </ApiContext.Provider>
  );
}

function Current({ route }: { route: Route }) {
  switch (route.screen) {
    case "live":
      return <LiveScreen />;
    case "report":
      return <ReportScreen />;
    case "history":
      return <HistoryScreen />;
    case "settings":
      return <SettingsScreen />;
    default:
      return <NewRunScreen />;
  }
}
