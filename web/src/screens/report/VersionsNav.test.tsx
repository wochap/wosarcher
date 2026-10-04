import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QUERY, RUN_ID } from "../../test/fixtures/sample";
import { REWRITE_ID, versions } from "../../test/fixtures/versions";
import { openScenario, play } from "../../test/scenario";

describe("VersionsNav", () => {
  it("lists the lineage with the viewed version current and the parent note", async () => {
    const { api } = await openScenario(versions);
    await play(RUN_ID, api.data.events[RUN_ID]);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    const nav = await screen.findByRole("navigation", { name: "Report versions" });
    expect(within(nav).getByRole("button", { name: "Help: Versions" })).toBeTruthy();
    const buttons = within(nav)
      .getAllByRole("button")
      .filter((b) => !b.dataset.help);
    expect(buttons.map((b) => b.textContent)).toEqual([
      `v1 · research${RUN_ID}full run · 2:30`,
      `v2 · rewrite${REWRITE_ID}Concise · 250 words · ¹ Superscript · 0:51`,
    ]);
    expect(buttons[1].getAttribute("aria-current")).toBe("true");
    expect(
      screen.getByText(/^Rewritten from r_8c21 \(v1\): same sources and passages; changed/)
        .textContent,
    ).toBe(
      "Rewritten from r_8c21 (v1): same sources and passages; changed Concise · 250 words · ¹ Superscript.",
    );
    expect(screen.getAllByRole("button", { name: /^Citation 1,/ })[0].textContent).toBe("¹");
    fireEvent.click(buttons[0]);
    expect(window.location.hash).toBe(`#/runs/${RUN_ID}`);
  });
});
