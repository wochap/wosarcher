import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { callsTo } from "../../test/fakeApi";
import { finished } from "../../test/fixtures/finished";
import { QUERY, RUN_ID } from "../../test/fixtures/sample";
import { openScenario } from "../../test/scenario";

async function openDialog() {
  const result = await openScenario(finished);
  await screen.findByRole("heading", { level: 1, name: QUERY });
  fireEvent.click(screen.getByRole("button", { name: "Rewrite" }));
  return result;
}

describe("RewriteDialog", () => {
  it("sends only the changed fields and opens the fork on Live run", async () => {
    const { api } = await openDialog();
    const dialog = screen.getByRole("dialog", { name: "Rewrite report" });
    expect(dialog.textContent).toContain("Reuses the 21 sources and 14 selected passages");
    expect(dialog.textContent).toContain(`Creates v2 linked to ${RUN_ID}`);
    const words = screen.getByLabelText("Length (words)");
    fireEvent.change(words, { target: { value: "250" } });
    fireEvent.blur(words);
    expect(screen.getByText("changed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Help: Changed" }));
    expect(screen.getByRole("tooltip").textContent).toContain(
      "This value differs from the version you are rewriting.",
    );
    expect(screen.getByText("was 1200 words")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Rewrite from write stage" }));
    });
    expect(callsTo(api, "forkRun")).toEqual([[RUN_ID, { from: "write", writing: { words: 250 } }]]);
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("closes without a request on Escape, Cancel, close, and backdrop", async () => {
    const { api } = await openDialog();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    for (const close of ["Cancel", "Close"]) {
      fireEvent.click(screen.getByRole("button", { name: "Rewrite" }));
      fireEvent.click(screen.getByRole("button", { name: close }));
      expect(screen.queryByRole("dialog")).toBeNull();
    }
    fireEvent.click(screen.getByRole("button", { name: "Rewrite" }));
    fireEvent.click(screen.getByRole("dialog").parentElement as HTMLElement);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(callsTo(api, "forkRun")).toEqual([]);
  });
});
