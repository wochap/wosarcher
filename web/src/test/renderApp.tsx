// Renders the whole app on a fake API, at a given screen.
import { render } from "@testing-library/react";
import type { ApiClient } from "../api/client";
import type { SocketFactory } from "../api/events";
import { App } from "../app/App";
import { FakeWebSocket } from "./FakeWebSocket";
import { type FakeApi, fakeApi } from "./fakeApi";

type Options = {
  hash?: string;
  api?: FakeApi;
  /** Lets a test reach the app's lock callback, as the HTTP client does on 401. */
  wrap?: (api: FakeApi, onUnauthorized: () => void) => ApiClient;
};

export function renderApp({ hash = "#/new", api = fakeApi(), wrap }: Options = {}) {
  window.location.hash = hash;
  FakeWebSocket.reset();
  const makeApi = (onUnauthorized: () => void) => (wrap ? wrap(api, onUnauthorized) : api);
  const result = render(
    <App makeApi={makeApi} Socket={FakeWebSocket as unknown as SocketFactory} />,
  );
  return { ...result, api };
}
