// Screens live in the URL fragment: #/new, #/live, #/live/<id>, #/runs/<id>, #/history,
// #/settings (and #/preview/<name> in development). Anything else is #/new.
import { useEffect, useState } from "react";

export type Screen = "new" | "live" | "report" | "history" | "settings";
export type Route = { screen: Screen; runId?: string } | { screen: "preview"; name: string };

export function parseRoute(hash: string): Route {
  const [, first, second] = hash.replace(/^#/, "").split("/");
  const id = second ? decodeURIComponent(second) : undefined;
  if (first === "live") return id ? { screen: "live", runId: id } : { screen: "live" };
  if (first === "runs" && id) return { screen: "report", runId: id };
  if (first === "history" || first === "settings" || first === "new") return { screen: first };
  if (first === "preview" && id) return { screen: "preview", name: id };
  return { screen: "new" };
}

export function routeHash(route: Route): string {
  if (route.screen === "preview") return `#/preview/${route.name}`;
  if (route.screen === "report") return `#/runs/${encodeURIComponent(route.runId ?? "")}`;
  if (route.screen === "live" && route.runId) return `#/live/${encodeURIComponent(route.runId)}`;
  return `#/${route.screen}`;
}

export function go(route: Route) {
  window.location.hash = routeHash(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", update);
    update();
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
