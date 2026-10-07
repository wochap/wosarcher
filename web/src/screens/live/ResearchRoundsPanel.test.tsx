import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ev } from "../../test/events";
import { roundsLog, roundTwoFetching, until } from "../../test/rounds";
import { viewOf } from "../../test/views";
import { ResearchRoundsPanel } from "./ResearchRoundsPanel";
import { SourcesPanel } from "./SourcesPanel";

const round = (k: number) => screen.getByText(`Round ${k}`).closest("li") as HTMLElement;

describe("ResearchRoundsPanel", () => {
  it("shows the live round, the earlier round's gap note, and the rounds left", () => {
    render(<ResearchRoundsPanel run={viewOf(roundTwoFetching())} planned={3} />);
    expect(screen.getByText("round 2/3")).toBeTruthy();
    expect(round(1).textContent).toContain("16 new pages · 32 kept");
    expect(round(1).textContent).toContain("Benchmarks are thin.");
    expect(round(1).textContent).toContain("Gap: 2 follow-up queries for round 2 · 2 uncovered");
    expect(round(2).textContent).toContain("6 new pages · fetching");
    expect(round(2).textContent).toContain("gap follow-ups");
    expect(screen.getByText("1 more round to go")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Research rounds" })).toBeTruthy();
  });

  it("lists the topic first in round 1 and counts it in the collapse", () => {
    const log = until(roundsLog("max"), (e) => e.type === "gap.ready");
    render(<ResearchRoundsPanel run={viewOf(log)} planned={3} />);
    const ids = () =>
      [...round(1).querySelectorAll("ol li")].map((li) => li.firstChild?.textContent);
    expect(ids()).toEqual(["q0", "q1"]);
    expect(round(1).textContent).toContain("Topic line");
    expect(screen.getByRole("button", { name: "Help: Topic line" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "+4 more" }));
    expect(ids()).toEqual(["q0", "q1", "q2", "q3", "q4", "q5"]);
    expect(screen.getByRole("button", { name: "Show fewer" })).toBeTruthy();
  });

  it("explains a stop for no new sources", () => {
    render(<ResearchRoundsPanel run={viewOf(roundsLog("nonew"))} planned={4} />);
    expect(round(2).textContent).toContain("0 new pages · 9 already fetched");
    expect(round(2).textContent).toContain("Gap: 1 follow-up query for round 3 · 2 uncovered");
    expect(round(3).textContent).toContain("0 new pages · 3 already fetched");
    expect(screen.getByText("Stopped after round 3 of 4 · no new sources")).toBeTruthy();
    expect(
      screen.getByText("Follow-up searches returned only pages fetched in earlier rounds."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Why research stopped" })).toBeTruthy();
    expect(screen.getByText("3 of 4 rounds")).toBeTruthy();
  });

  it("explains a stop for no follow-ups", () => {
    render(<ResearchRoundsPanel run={viewOf(roundsLog("nofollow"))} planned={3} />);
    expect(round(2).textContent).toContain("Gap: no usable follow-up query · 2 uncovered");
    expect(screen.getByText("Stopped after round 2 of 3 · no follow-ups")).toBeTruthy();
    expect(screen.getByText("The gap step wrote no usable follow-up query.")).toBeTruthy();
  });

  it("lists the missing parts under the gap note", () => {
    render(<ResearchRoundsPanel run={viewOf(roundTwoFetching())} planned={3} />);
    const note = screen.getByText("Benchmarks are thin.");
    expect(note.nextElementSibling?.textContent).toBe("Missing: setup; cost");
    expect(note.nextElementSibling?.className).toBe(note.className);
  });

  it("shows no missing line when the gap step named no part", () => {
    render(<ResearchRoundsPanel run={viewOf(roundsLog("max"))} planned={3} />);
    expect(round(2).textContent).toContain("Latency is unclear.");
    expect(round(2).textContent).not.toContain("Missing:");
  });

  it("ends with every round run and no end note", () => {
    render(<ResearchRoundsPanel run={viewOf(roundsLog("max"))} planned={3} />);
    expect(screen.getByText("All 3 rounds ran · max rounds")).toBeTruthy();
    expect(round(2).textContent).toContain("Gap: 1 follow-up query for round 3");
    expect(round(2).textContent).not.toContain("uncovered");
    expect(screen.queryByText(/more round/)).toBeNull();
  });

  it("waits for the planner before round 1", () => {
    const log = roundsLog().slice(0, 2);
    render(<ResearchRoundsPanel run={viewOf(log)} planned={3} />);
    expect(screen.getByText("Planning round 1 queries…")).toBeTruthy();
  });

  it("says cancelled when the run is cancelled", () => {
    const log = [...roundTwoFetching(), ev(999, "run.cancelled", { stage: "fetch" })];
    render(<ResearchRoundsPanel run={viewOf(log)} planned={3} />);
    expect(screen.getByText("cancelled")).toBeTruthy();
    expect(round(2).textContent).toContain("cancelled · 6 new pages");
  });
});

describe("SourcesPanel round tags", () => {
  it("tags a page a later round fetched", () => {
    const run = viewOf(roundTwoFetching());
    render(<SourcesPanel run={run} files={[]} context={null} rounds={3} />);
    const row = screen.getByText("https://r2-0.test").closest("div")?.parentElement;
    expect(row?.textContent).toContain("round 2");
    const first = screen.getByText("https://r1-0.test").closest("div")?.parentElement;
    expect(first?.textContent).not.toContain("round");
  });
});
