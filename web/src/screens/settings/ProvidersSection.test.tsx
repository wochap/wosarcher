import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ProviderEntry, ProvidersReport } from "../../api/types";
import { callsTo, type FakeApi, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

const card = (name: string, block: string) =>
  screen.getByRole("region", { name: `${name} (${block})` });
const strip = (name: string, block: string) => within(card(name, block)).getByRole("status");
const group = (label: string) => screen.getByRole("group", { name: label });
const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();
const loaded = () => screen.findByText(/^Slow · checked/);
const entryOf = (api: FakeApi, block: string, name: string) =>
  api.data.providers.entries.find((e) => e.block === block && e.name === name) as ProviderEntry;

/** Replaces `checkProviders` with one that waits; returns the function that answers it. */
function holdChecks(api: FakeApi): () => (report: ProvidersReport) => void {
  let finish: (report: ProvidersReport) => void = () => {};
  api.checkProviders = (entries) => {
    api.calls.push({ method: "checkProviders", args: [entries] });
    return new Promise((resolve) => (finish = resolve));
  };
  return () => finish;
}

describe("ProvidersSection", () => {
  it("opening Settings reads the stored report and posts no check", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    expect(callsTo(api, "listProviders").length).toBeGreaterThan(0);
    expect(callsTo(api, "checkProviders")).toHaveLength(0);
  });

  it("Grouped entries: one group per block with a card per entry", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Search", "Fetch", "Prefilter", "Scorer", "LLM"]);
    const scorer = within(group("Scorer"));
    expect(scorer.getAllByRole("region")).toHaveLength(3);
    const bm25 = within(group("Scorer")).getByRole("region", { name: "bm25 (score)" });
    expect(bm25.textContent).toContain("Built in, nothing to check.");
    expect(within(bm25).queryByRole("button", { name: /^Check/ })).toBeNull();
    expect(within(bm25).queryByRole("status")).toBeNull();
    expect(within(group("LLM")).getAllByRole("region")).toHaveLength(2);
    expect(
      within(group("Prefilter")).getByRole("region", { name: "none (prefilter)" }),
    ).toBeTruthy();
    for (const label of ["Search", "Fetch", "Prefilter", "Scorer", "LLM"])
      expect(within(group(label)).getByRole("button", { name: `Help: ${label}` })).toBeTruthy();
  });

  it("LLM models: lists each model's limits, the default first", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    const items = within(card("omniroute", "llm")).getAllByRole("listitem");
    expect(items[0].textContent).toBe("research-smartdefault1,048,576 window · 32,768 out");
    expect(items[2].textContent).toBe("qwen3-30b-a3bfallback limits");
    expect(within(items[2]).getByText("fallback limits").className).toMatch(/faint/);
    expect(within(card("omniroute", "llm")).queryByText("Model")).toBeNull();
  });

  it("shows an unchecked entry as Not checked yet on a dashed strip", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    expect(strip("rerank", "score").textContent).toContain("Not checked yet");
    expect(strip("rerank", "score").dataset.state).toBe("unchecked");
  });

  it("shows a slow provider with its age and latency against the limit", async () => {
    const api = fakeApi();
    entryOf(api, "search", "searxng").checked_at = minutesAgo(3);
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Slow · checked 3m ago");
    expect(strip("searxng", "search").dataset.state).toBe("degraded");
    expect(strip("searxng", "search").textContent).toContain("1,840 ms, limit 1,000 ms");
  });

  it("shows a down provider with the error in the mono font", async () => {
    const api = fakeApi();
    Object.assign(entryOf(api, "fetch", "firecrawl"), {
      status: "down",
      detail: "ECONNREFUSED",
      checked_at: new Date().toISOString(),
    });
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Down · checked just now");
    expect(strip("firecrawl", "fetch").dataset.state).toBe("down");
    expect(within(strip("firecrawl", "fetch")).getByText("ECONNREFUSED").className).toMatch(/mono/);
  });

  it("shows OK with the latency", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    expect(strip("embeddings", "prefilter").textContent).toContain("OK · checked");
    expect(strip("embeddings", "prefilter").textContent).toContain("38 ms");
  });

  it("shows an entry's error in place of its list", async () => {
    const api = fakeApi();
    entryOf(api, "score", "jev-strict").error = "api_key_file: no such file";
    renderApp({ hash: "#/settings", api });
    await loaded();
    const jev = within(card("jev-strict", "score"));
    expect(jev.getByText("api_key_file: no such file")).toBeTruthy();
    expect(jev.queryByText("Base URL")).toBeNull();
  });

  it("Check one card: posts that entry only and only that card checks", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    const check = api.checkProviders;
    const finish = holdChecks(api);
    fireEvent.click(screen.getByRole("button", { name: "Check jev-strict (score)" }));
    expect(callsTo(api, "checkProviders")).toEqual([[["score/jev-strict"]]]);
    expect(screen.getAllByText("Checking…")).toHaveLength(1);
    expect(strip("jev-strict", "score").textContent).toContain("Checking…");
    expect(
      (screen.getByRole("button", { name: "Check jev-strict (score)" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(strip("rerank", "score").textContent).toContain("Not checked yet");
    expect(strip("searxng", "search").textContent).toContain("Slow · checked");
    const report = await check(["score/jev-strict"]);
    await act(async () => finish()(report));
    expect(screen.queryByText("Checking…")).toBeNull();
    expect(strip("jev-strict", "score").textContent).toContain("OK · checked just now");
    expect(strip("rerank", "score").textContent).toContain("Not checked yet");
  });

  it("Check all posts one check with no entries, every endpoint card checking meanwhile", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    const finish = holdChecks(api);
    fireEvent.click(screen.getByRole("button", { name: "Check all providers" }));
    expect(callsTo(api, "checkProviders")).toEqual([[undefined]]);
    expect(screen.getAllByText("Checking…")).toHaveLength(7);
    for (const button of screen.getAllByRole("button", { name: /^Check / }))
      expect((button as HTMLButtonElement).disabled).toBe(true);
    await act(async () => finish()(api.data.providers));
    expect(screen.queryByText("Checking…")).toBeNull();
  });

  it("keeps the strips and shows the error when a check fails", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    api.checkProviders = () => Promise.reject(new Error("doctor did not finish within 60 s"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Check all providers" }));
    });
    expect(screen.getByRole("alert").textContent).toBe("doctor did not finish within 60 s");
    expect(strip("searxng", "search").textContent).toContain("Slow · checked");
  });

  it("notes that checks run only on click", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    expect(
      screen.getByText("Checked only when you click, so idle GPU servers stay asleep."),
    ).toBeTruthy();
  });

  it("renders no secret field", async () => {
    const { container } = renderApp({ hash: "#/settings" });
    await loaded();
    expect(container.textContent).not.toMatch(/api[_ ]?key|secret/i);
  });

  it("explains Health in the card's strip", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    fireEvent.mouseEnter(
      within(strip("rerank", "score")).getByRole("button", { name: "Help: Health" }),
    );
    expect(screen.getByRole("tooltip").textContent).toContain(
      "Not checked yet, OK, slow (degraded), down, or skipped (built in, no endpoint). Checks run only when you click Check, so idle GPU servers are never woken by opening this page.",
    );
  });

  it("lists Device and Unload with their help", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    const rerank = within(card("rerank", "score"));
    expect(rerank.getByText("desktop:gpu0")).toBeTruthy();
    expect(rerank.getByText("llama-swap")).toBeTruthy();
    for (const label of ["Device", "Unload", "Health"])
      expect(rerank.getByRole("button", { name: `Help: ${label}` })).toBeTruthy();
  });

  it("shows the default profile with its entries and the GPU policy", async () => {
    const { container } = renderApp({ hash: "#/settings" });
    await loaded();
    await screen.findByText("searxng · firecrawl · embeddings · rerank · agents");
    expect(container.textContent).toContain(
      "Default profilelow-vramsearxng · firecrawl · embeddings · rerank · agents",
    );
    expect(container.textContent).not.toContain("Models take turns");
    expect(screen.getByRole("button", { name: "Help: Profile" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: GPU policy" })).toBeTruthy();
    const exclusive = screen.getByLabelText("Exclusive") as HTMLInputElement;
    expect(exclusive.checked).toBe(true);
    expect(exclusive.disabled).toBe(true);
    expect((screen.getByLabelText("Shared") as HTMLInputElement).disabled).toBe(true);
    expect(
      screen.getByText("Each model unloads before the next one loads on desktop:gpu0."),
    ).toBeTruthy();
  });
});
