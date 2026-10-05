import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ev } from "../../test/events";
import { renderWithHelp } from "../../test/help";
import { viewOf } from "../../test/views";
import { SubQueriesPanel } from "./SubQueriesPanel";

const TOPIC = "speculative decoding: draft-model size vs acceptance on 8–12 GB GPUs";
const log = [
  ev(1, "run.started", { query: "q", profile: "p", parent_run_id: null, version: 1, until: null }),
  ev(2, "plan.ready", {
    queries: [
      { id: "q0", text: TOPIC },
      { id: "q1", text: "a" },
      { id: "q2", text: "b" },
      { id: "q3", text: "c" },
    ],
  }),
];

describe("SubQueriesPanel", () => {
  it("numbers rows by query ID and labels the topic row", () => {
    renderWithHelp(<SubQueriesPanel run={viewOf(log)} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows.map((li) => li.firstChild?.textContent)).toEqual(["q0", "q1", "q2", "q3"]);
    const topic = rows[0].children[1];
    expect(topic.firstChild?.textContent).toBe("Topic line");
    expect(topic.textContent).toBe(`Topic line${TOPIC}`);
    expect(screen.getByText("0/4")).toBeTruthy();
  });

  it("explains the topic line", () => {
    renderWithHelp(<SubQueriesPanel run={viewOf(log)} />);
    fireEvent.focus(screen.getByRole("button", { name: "Help: Topic line" }));
    const tip = screen.getByRole("tooltip").textContent;
    expect(tip).toContain("Topic line");
    expect(tip).toContain(
      "A short topic the planner writes from your question. Passages are ranked against it as the first query, q0. Questions up to 200 characters are searched as written; longer ones are searched by this topic.",
    );
  });
});
