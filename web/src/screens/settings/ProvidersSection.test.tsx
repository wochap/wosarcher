import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HealthReport } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

const card = (role: string) => screen.getByRole("region", { name: role });
const strip = (role: string) => within(card(role)).getByRole("status");

describe("ProvidersSection", () => {
  it("shows each health state with its text and tint", async () => {
    const api = fakeApi();
    api.data.health.checks[1] = {
      ...api.data.health.checks[1],
      status: "down",
      detail: "ECONNREFUSED",
    };
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Slow · 1,840 ms · probe over 1000 ms");
    expect(strip("Search").dataset.state).toBe("degraded");
    expect(strip("Fetch").textContent).toContain("Unreachable · ECONNREFUSED");
    expect(strip("Fetch").dataset.state).toBe("down");
    expect(strip("Embeddings").textContent).toContain("Healthy · 38 ms");
    expect(strip("LLM").textContent).toContain("just now");
    expect(within(card("Scorer")).getByText("bge-reranker-v2-m3-Q8_0.gguf")).toBeTruthy();
    expect(screen.getByText(/devices gpu0/)).toBeTruthy();
  });

  it("shows skipped providers", async () => {
    renderApp({ hash: "#/settings" });
    expect((await screen.findByText("Skipped · built in")).closest("[data-state]")).toBeTruthy();
  });

  it("checks with one request, every card checking and every Check disabled meanwhile", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Slow · 1,840 ms · probe over 1000 ms");
    let finish: (report: HealthReport) => void = () => {};
    api.health = () => new Promise((resolve) => (finish = resolve));
    fireEvent.click(within(card("Search")).getByRole("button", { name: "Check" }));
    expect(screen.getAllByText("Checking…")).toHaveLength(5);
    for (const button of screen.getAllByRole("button", { name: "Check" })) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    await act(async () => finish(api.data.health));
    expect(screen.queryByText("Checking…")).toBeNull();
  });

  it("Check all sends one health request", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await screen.findByText("Slow · 1,840 ms · probe over 1000 ms");
    const before = callsTo(api, "health").length;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Check all providers" }));
    });
    expect(callsTo(api, "health").length).toBe(before + 1);
  });

  it("renders no secret field", async () => {
    const { container } = renderApp({ hash: "#/settings" });
    await screen.findByText("Slow · 1,840 ms · probe over 1000 ms");
    expect(container.textContent).not.toMatch(/api[_ ]?key|secret/i);
  });
});
