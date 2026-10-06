// The three app contexts: the API (client and socket factory), authentication, and UI state.
import { type Context, createContext, useContext } from "react";
import type { ApiClient } from "../api/client";
import type { SocketFactory } from "../api/events";
import type { DomainLists, ResearchValues, WritingOptions } from "../api/types";
import type { Help } from "../components/help";
import type { Depth } from "../run/depth";
import type { Recipe } from "../run/format";
import type { LlmValues } from "../run/thinking";
import type { LiveRun } from "../run/useRun";
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

export type OverlayKind = "help" | "alertdialog" | "dialog" | "tooltip";
/** `error`: the danger-colored warning icon in place of the check. */
export type ToastOptions = { undo?: () => void; error?: boolean };

export type RunOptions = {
  recipe: Recipe;
  sources: "web" | "files" | "both";
  profile: string;
  depth: Depth;
};

/** The New run form, kept while the user visits other screens. Options hold overrides only. */
export type Draft = {
  query: string;
  files: File[];
  options: Partial<RunOptions>;
  writing: Partial<WritingOptions>;
  /** Domain lists the user edited; an unedited list follows its default. */
  domains: Partial<DomainLists>;
  /** The search language as typed; empty sends none. */
  searchLanguage: string;
  /** The Custom depth's values and its default Length, once Custom was picked or edited. */
  custom?: { values: ResearchValues; words: number };
  /** The Model group's values, once edited; until then the stored ones. */
  llm?: LlmValues;
};
export const EMPTY_DRAFT: Draft = {
  query: "",
  files: [],
  options: {},
  writing: {},
  domains: {},
  searchLanguage: "",
};

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
  live: LiveRun;
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

/** The open help tooltip: its key, the button it belongs to, and that button's rectangle. */
export type HelpState = {
  key: string;
  owner: string;
  rect: DOMRect;
  pinned: boolean;
  /** Help built at run time; shown instead of the `HELP` entry for `key`. */
  entry?: Help;
};

export type HelpUi = {
  help: HelpState | null;
  openHelp(help: HelpState): void;
  closeHelp(): void;
  /** Closes the tooltip after 140 ms unless it is pinned or `keepHelp` runs first. */
  leaveHelp(): void;
  keepHelp(): void;
};
/** Optional: components rendered without the app show their help buttons inert. */
export const HelpContext = createContext<HelpUi | null>(null);

function useRequired<T>(context: Context<T | null>, name: string): T {
  const value = useContext(context);
  if (!value) throw new Error(`${name} is not provided`);
  return value;
}

export const useServices = () => useRequired(ApiContext, "ApiContext");
export const useApi = () => useServices().api;
export const useAuth = () => useRequired(AuthContext, "AuthContext");
export const useUi = () => useRequired(UiContext, "UiContext");
export const useHelp = () => useContext(HelpContext);
