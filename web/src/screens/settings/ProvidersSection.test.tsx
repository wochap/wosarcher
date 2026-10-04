import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HealthReport } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

const card = (role: string) => screen.getByRole("region", { name: role });
const strip = (role: string) => within(card(role)).getByRole("status");
const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();
const loaded = () => screen.findByText(/^Slow · checked/);

describe("ProvidersSection", () => {
  it("opening Settings reads the stored report and posts no check", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    expect(callsTo(api, "health").length).toBeGreaterThan(0);
    expect(callsTo(api, "checkHealth")).toHaveLength(0);
  });

  it("shows an unchecked block as Not checked yet on a dashed strip", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    expect(strip("Scorer").textContent).toContain("Not checked yet");
    expect(strip("Scorer").dataset.state).toBe("unchecked");
  });

  it("shows a slow provider with its age and latency against the limit", async () => {
    const api = fakeApi();
    api.data.health.checks[0].checked_at = minutesAgo(3);
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Slow · checked 3m ago");
    expect(strip("Search").dataset.state).toBe("degraded");
    expect(strip("Search").textContent).toContain("1,840 ms, limit 1,000 ms");
  });

  it("shows a down provider with the error in the mono font", async () => {
    const api = fakeApi();
    api.data.health.checks[1] = {
      ...api.data.health.checks[1],
      status: "down",
      detail: "ECONNREFUSED",
      checked_at: new Date().toISOString(),
    };
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Down · checked just now");
    expect(strip("Fetch").dataset.state).toBe("down");
    expect(within(strip("Fetch")).getByText("ECONNREFUSED").className).toMatch(/mono/);
  });

  it("shows OK with the latency", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    expect(strip("Embeddings").textContent).toContain("OK · checked");
    expect(strip("Embeddings").textContent).toContain("38 ms");
  });

  it("shows skipped providers", async () => {
    renderApp({ hash: "#/settings" });
    expect((await screen.findByText("Skipped · built in")).closest("[data-state]")).toBeTruthy();
  });

  it("Check on a card checks only that block", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    const check = api.checkHealth;
    let finish: (report: HealthReport) => void = () => {};
    api.checkHealth = (blocks, profile) => {
      api.calls.push({ method: "checkHealth", args: [blocks, profile] });
      return new Promise((resolve) => (finish = resolve));
    };
    fireEvent.click(screen.getByRole("button", { name: "Check Scorer provider" }));
    expect(callsTo(api, "checkHealth")[0][0]).toEqual(["score"]);
    expect(screen.getAllByText("Checking…")).toHaveLength(1);
    expect(strip("Scorer").textContent).toContain("Checking…");
    expect(
      (screen.getByRole("button", { name: "Check Scorer provider" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(strip("Search").textContent).toContain("Slow · checked");
    const report = await check(["score"]);
    await act(async () => finish(report));
    expect(screen.queryByText("Checking…")).toBeNull();
    expect(strip("Scorer").textContent).toContain("OK · checked just now");
  });

  it("Check all posts one check for every block, every card checking meanwhile", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    let finish: (report: HealthReport) => void = () => {};
    api.checkHealth = (blocks, profile) => {
      api.calls.push({ method: "checkHealth", args: [blocks, profile] });
      return new Promise((resolve) => (finish = resolve));
    };
    fireEvent.click(screen.getByRole("button", { name: "Check all providers" }));
    expect(callsTo(api, "checkHealth")).toHaveLength(1);
    expect(callsTo(api, "checkHealth")[0][0]).toBeUndefined();
    expect(screen.getAllByText("Checking…")).toHaveLength(5);
    for (const button of screen.getAllByRole("button", { name: /^Check / }))
      expect((button as HTMLButtonElement).disabled).toBe(true);
    await act(async () => finish(api.data.health));
    expect(screen.queryByText("Checking…")).toBeNull();
  });

  it("keeps the strips and shows the error when a check fails", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await loaded();
    api.checkHealth = () => Promise.reject(new Error("doctor did not finish within 60 s"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Check all providers" }));
    });
    expect(screen.getByRole("alert").textContent).toBe("doctor did not finish within 60 s");
    expect(strip("Search").textContent).toContain("Slow · checked");
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

  it("titles the cards by the server's block names", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    for (const title of ["Search", "Fetch", "Embeddings", "Scorer", "LLM"])
      expect(card(title)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "prefilter" })).toBeNull();
    expect(screen.queryByRole("region", { name: "score" })).toBeNull();
  });

  it("titles a keyword prefilter Prefilter", async () => {
    const api = fakeApi();
    api.data.health.checks[2] = { ...api.data.health.checks[2], provider: "bm25" };
    renderApp({ hash: "#/settings", api });
    await loaded();
    expect(within(card("Prefilter")).getByText("bm25")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Embeddings" })).toBeNull();
  });

  it("explains Health in the card's strip", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    fireEvent.mouseEnter(within(strip("Scorer")).getByRole("button", { name: "Help: Health" }));
    expect(screen.getByRole("tooltip").textContent).toContain(
      "Not checked yet, OK, slow (degraded), down, or skipped (built in, no endpoint). Checks run only when you click Check, so idle GPU servers are never woken by opening this page.",
    );
  });

  it("lists Device and Unload with their help", async () => {
    renderApp({ hash: "#/settings" });
    await loaded();
    const scorer = within(card("Scorer"));
    expect(scorer.getByText("desktop:gpu0")).toBeTruthy();
    expect(scorer.getByText("llama-swap")).toBeTruthy();
    for (const label of ["Device", "Unload", "Health"])
      expect(scorer.getByRole("button", { name: `Help: ${label}` })).toBeTruthy();
  });

  it("shows the active profile with its description and the GPU policy", async () => {
    const { container } = renderApp({ hash: "#/settings" });
    await loaded();
    await screen.findByText("· Models take turns on one small GPU; slower, fits 8 GB.");
    expect(container.textContent).toContain(
      "Active profilelow-vram· Models take turns on one small GPU; slower, fits 8 GB.",
    );
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
