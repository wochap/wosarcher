// The three app contexts: the API (client and socket factory), authentication, and UI state.
import { type Context, createContext, useContext } from "react";
import type { ApiClient } from "../api/client";
import type { Conn, SocketFactory } from "../api/events";
import type { WritingOptions } from "../api/types";
import type { RunView } from "../run/reducer";
import type { Theme } from "./theme";

export type Services = { api: ApiClient; Socket?: SocketFactory };
export const ApiContext = createContext<Services | null>(null);

export type Auth = {
  locked: boolean;
  /** `none` when no password is set: the app never locks. */
  method: "cookie" | "token" | "none" | null;
  lock(): void;
  unlock(): void;
};
export const AuthContext = createContext<Auth | null>(null);

export type OverlayKind = "alertdialog" | "dialog" | "tooltip";
export type ToastOptions = { undo?: () => void };

export type RunOptions = {
  recipe: "report" | "context";
  sources: "web" | "files" | "both";
  profile: string;
};

/** The New run form, kept while the user visits other screens. Options hold overrides only. */
export type Draft = {
  query: string;
  files: File[];
  options: Partial<RunOptions>;
  writing: Partial<WritingOptions>;
};
export const EMPTY_DRAFT: Draft = { query: "", files: [], options: {}, writing: {} };

export type LiveTab = "progress" | "sources" | "passages" | "report";

export type Ui = {
  theme: Theme;
  toggleTheme(): void;
  isPhone: boolean;
  toast(message: string, options?: ToastOptions): void;
  /** Registers an open overlay that Escape closes; returns the unregister function. */
  overlay(kind: OverlayKind, close: () => void): () => void;
  /** The run "Live run" opens and whose stream stays open on every screen. */
  followed: string | null;
  follow(runId: string | null): void;
  /** The followed run's view and connection. */
  live: { view: RunView | null; conn: Conn };
  draft: Draft;
  setDraft(update: (draft: Draft) => Draft): void;
  /** The Live run tab shown below 720px. */
  liveTab: LiveTab;
  setLiveTab(tab: LiveTab): void;
  /** Whether the last provider health result had a provider that is not healthy. */
  healthWarn: boolean;
  setHealthWarn(warn: boolean): void;
  /** Runs deleted, or waiting for their delete toast to expire; History hides them. */
  hiddenRuns: ReadonlySet<string>;
  /** Hides the run and deletes it on the server unless Undo is pressed within 6 s. */
  deleteRun(runId: string): void;
};
export const UiContext = createContext<Ui | null>(null);

function useRequired<T>(context: Context<T | null>, name: string): T {
  const value = useContext(context);
  if (!value) throw new Error(`${name} is not provided`);
  return value;
}

export const useServices = () => useRequired(ApiContext, "ApiContext");
export const useApi = () => useServices().api;
export const useAuth = () => useRequired(AuthContext, "AuthContext");
export const useUi = () => useRequired(UiContext, "UiContext");
