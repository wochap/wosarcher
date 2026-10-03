import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { cancelled } from "../../test/fixtures/cancelled";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { CONTEXT, RUN_ID, upTo } from "../../test/fixtures/sample";
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
