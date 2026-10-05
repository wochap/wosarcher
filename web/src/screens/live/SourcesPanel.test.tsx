import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { cancelled } from "../../test/fixtures/cancelled";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { CONTEXT, Log, RUN_ID, upTo } from "../../test/fixtures/sample";
import { viewOf } from "../../test/views";
import { SourcesPanel } from "./SourcesPanel";
import { SubQueriesPanel } from "./SubQueriesPanel";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const row = (text: string) =>
  screen.getByText(text).closest("div[class]")?.parentElement as HTMLElement;
const files = [{ sourceId: "f1", title: "bench-3060.md", uri: "notes/bench-3060.md", size: 4403 }];

describe("SourcesPanel", () => {
  it("shows a failed page in the danger tone and the failure note", () => {
    let pages = 0;
    const events = upTo(all, (e) => e.type === "page.fetched" && ++pages === 14);
    render(<SourcesPanel run={viewOf(events)} files={files} context={null} />);
    expect(screen.getByText("403 Forbidden").dataset.tone).toBe("danger");
    expect(screen.getByText("1 failed · run continues")).toBeTruthy();
    expect(screen.getByText("13 of 22 fetched · 1 files")).toBeTruthy();
    expect(screen.getByText("4.3 KB")).toBeTruthy();
    expect(screen.getAllByText("found").length).toBeGreaterThan(0);
  });

  it("lists newest first and counts kept passages once selected", () => {
    render(<SourcesPanel run={viewOf(all)} files={files} context={CONTEXT} />);
    const titles = screen.getAllByRole("link").map((a) => a.textContent);
    expect(titles[0]).toBe("Better & Faster Large Language Models via Multi-token Prediction");
    expect(row("Decoding Speculative Decoding").textContent).toContain("1 kept");
    expect(screen.getByText("bench-3060.md").parentElement?.parentElement?.textContent).toContain(
      "1 kept",
    );
  });

  it("shows unfetched sources of a cancelled run as not fetched", () => {
    render(
      <SourcesPanel
        run={viewOf(cancelled.data.events?.[RUN_ID] as RunEvent[])}
        files={[]}
        context={null}
      />,
    );
    expect(screen.getAllByText("not fetched")).toHaveLength(14);
  });

  it("shows the union of query IDs with their text, and thin pages", () => {
    const url = "https://www.gob.pe/371-inscribir-alerta-registral";
    const log = new Log("r1");
    log.add("run.started", {
      query: "q",
      profile: "p",
      parent_run_id: null,
      until: null,
      version: 1,
    });
    log.add("plan.ready", { queries: [{ id: "q4", text: "alerta registral" }] }, "plan");
    log.add("hit.found", { url, title: "Alerta registral", query_ids: ["q4"] }, "search");
    log.add("gap.ready", {
      round: 1,
      queries: [{ id: "q7", text: "inscribir alerta registral requisitos" }],
      note: "",
      uncovered: [],
      retried: false,
    } as never);
    log.add("hit.found", { url, title: "Alerta registral", query_ids: ["q7", "q4"] }, "search");
    log.add(
      "page.fetched",
      { url, title: "Alerta registral", source_id: "s1", cached: false, chars: 94, thin: true },
      "fetch",
    );
    render(<SourcesPanel run={viewOf(log.events)} files={[]} context={null} />);
    const r = row("Alerta registral");
    expect(r.textContent).toContain("q4 · q7");
    expect(screen.getByText("q7").title).toBe("inscribir alerta registral requisitos");
    expect(screen.getByText("q7").tabIndex).toBe(0);
    expect(screen.getByText("thin")).toBeTruthy();
    expect(screen.getByText("1 of 1 fetched · 0 files")).toBeTruthy();
  });

  it("shows six skeleton rows while queued", () => {
    render(
      <SourcesPanel
        run={viewOf(loading.data.events?.[RUN_ID] as RunEvent[], RUN_ID)}
        files={[]}
        context={null}
      />,
    );
    expect(screen.getAllByTestId("skeleton")).toHaveLength(6);
  });
});

describe("SubQueriesPanel", () => {
  it("shows results per sub-query and the summary", () => {
    render(<SubQueriesPanel run={viewOf(all)} />);
    expect(screen.getByText("5/5")).toBeTruthy();
    expect(screen.getAllByText(/\d results/)).toHaveLength(5);
  });

  it("waits for the planner while queued", () => {
    render(<SubQueriesPanel run={viewOf(loading.data.events?.[RUN_ID] as RunEvent[], RUN_ID)} />);
    expect(screen.getByText("Waiting for the planner…")).toBeTruthy();
  });
});
