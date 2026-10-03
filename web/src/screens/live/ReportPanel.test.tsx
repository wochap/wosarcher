import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { CitationTooltip, tooltipPlace } from "../../run/CitationTooltip";
import { ev } from "../../test/events";
import { writing } from "../../test/fixtures/data";
import { live } from "../../test/fixtures/live";
import { CONTEXT, RUN_ID, upTo } from "../../test/fixtures/sample";
import { viewOf } from "../../test/views";
import { ReportPanel } from "./ReportPanel";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const delta = (text: string) => ev(999, "report.delta", { text }, "write", RUN_ID);

function panel(events: RunEvent[], onCite: (n: number) => void = () => {}) {
  return render(
    <ReportPanel
      run={viewOf(events, RUN_ID)}
      report={null}
      context={CONTEXT}
      writing={writing}
      isPhone={false}
      onCite={onCite}
      onLeave={() => {}}
    />,
  );
}

describe("ReportPanel", () => {
  it("renders one chip per cited passage and the caret while writing", () => {
    const start = upTo(all, (e) => e.type === "report.delta");
    panel([...start, delta("## Summary\nSmall drafts win [1, 2] on GPUs [3"), delta("")]);
    expect(screen.getByRole("heading", { name: "Summary" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Citation \d, show passage/ })).toHaveLength(2);
    expect(screen.getByText("[2]")).toBeTruthy();
    expect(document.querySelector("[class*=caret]")).toBeTruthy();
    expect(screen.getByText(/writing · \d+ tokens/)).toBeTruthy();
    expect(screen.getByText("Analytical · 1200 words · English")).toBeTruthy();
  });

  it("shows no caret once written", () => {
    panel(all);
    expect(screen.getAllByRole("button", { name: /Citation/ }).length).toBeGreaterThan(10);
    expect(document.querySelector("[class*=caret]")).toBeNull();
  });

  it("explains what it waits for", () => {
    panel(upTo(all, (e) => e.type === "stage.started" && e.stage === "write"));
    expect(
      screen.getByText("Writer is waiting for the GPU while the scorer unloads."),
    ).toBeTruthy();
  });

  it("keeps scrolled to the bottom while within 140px of it", () => {
    const start = upTo(all, (e) => e.type === "report.delta");
    const { rerender } = panel([...start, delta("First line.")]);
    const body = screen.getByTestId("report-body");
    Object.defineProperty(body, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(body, "clientHeight", { configurable: true, value: 400 });
    body.scrollTop = 500;
    fireEvent.scroll(body);
    const props = {
      context: CONTEXT,
      report: null,
      writing,
      isPhone: false,
      onCite() {},
      onLeave() {},
    };
    rerender(
      <ReportPanel run={viewOf([...start, delta("First line. More.")], RUN_ID)} {...props} />,
    );
    expect(body.scrollTop).toBe(1000);
    body.scrollTop = 100;
    fireEvent.scroll(body);
    rerender(
      <ReportPanel
        run={viewOf([...start, delta("First line. More. Again.")], RUN_ID)}
        {...props}
      />,
    );
    expect(body.scrollTop).toBe(100);
  });

  it("reports a hovered chip's passage and rect", () => {
    const start = upTo(all, (e) => e.type === "report.delta");
    const cites: number[] = [];
    panel([...start, delta("Drafts [3].")], (n) => {
      cites.push(n);
    });
    act(() => {
      fireEvent.mouseEnter(screen.getByRole("button", { name: "Citation 3, show passage" }));
    });
    expect(cites).toEqual([3]);
  });
});

describe("CitationTooltip", () => {
  const rect = (top: number) => ({ left: 100, top, bottom: top + 16 }) as DOMRect;

  it("shows the passage's label, score, text, title, and domain", () => {
    render(<CitationTooltip cite={{ n: 3, rect: rect(100) }} context={CONTEXT} marker="numeric" />);
    const tip = screen.getByRole("tooltip");
    expect(tip.textContent).toContain("[3]");
    expect(tip.textContent).toContain("0.89");
    expect(tip.textContent).toContain("relevance");
    expect(tip.textContent).toContain("“On the RTX 3060 (12 GB)");
    expect(tip.textContent).toContain("bench-3060.md");
    expect(tip.textContent).toContain("notes/bench-3060.md · Results › Llama-3-8B Q4 + 160M draft");
    expect(tip.dataset.above).toBe("false");
  });

  it("goes above the chip when less than 230px remain below", () => {
    expect(tooltipPlace(rect(700), 1200, 800)).toEqual({ left: 80, top: 694, above: true });
    expect(tooltipPlace(rect(100), 1200, 800)).toEqual({ left: 80, top: 122, above: false });
    expect(tooltipPlace({ ...rect(100), left: 1190 } as DOMRect, 1200, 800).left).toBe(828);
  });
});
