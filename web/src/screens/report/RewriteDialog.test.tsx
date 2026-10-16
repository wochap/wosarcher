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
    expect(dialog.textContent).toContain("Reuses the 21 sources and 16 scored passages");
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
      fireEvent.click(screen.getByRole("button", { name: "Rewrite from select stage" }));
    });
    expect(callsTo(api, "forkRun")).toEqual([
      [RUN_ID, { from: "select", writing: { words: 250 } }],
    ]);
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("rewrites a report as an answer", async () => {
    const { api } = await openDialog();
    const format = screen.getByRole("radiogroup", { name: "Format" });
    expect(format.textContent).toBe("reportanswer");
    expect(screen.getByRole("button", { name: "Help: Format" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("answer"));
    expect(screen.getByText("was report")).toBeTruthy();
    const words = screen.getByLabelText("Length (words)");
    fireEvent.change(words, { target: { value: "400" } });
    fireEvent.blur(words);
    expect(screen.getAllByText("changed")).toHaveLength(2);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Rewrite from select stage" }));
    });
    expect(callsTo(api, "forkRun")).toEqual([
      [RUN_ID, { from: "select", writing: { format: "answer", words: 400 } }],
    ]);
  });

  it("rewrites with another model from the Model group", async () => {
    const { api } = await openDialog();
    const toggle = screen.getByRole("button", { name: "Model" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("Context tokens")).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByLabelText("Context tokens")).toBeTruthy();
    expect(screen.getByLabelText("Write thinking")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gemma-3-12b" } });
    expect(screen.getByText("edited")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Rewrite from select stage" }));
    });
    expect(callsTo(api, "forkRun")).toEqual([
      [RUN_ID, { from: "select", writing: {}, llm: { model: "gemma-3-12b" } }],
    ]);
  });

  it("shows the fallback and Context tokens notes in the Model group", async () => {
    await openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Model" }));
    await act(async () => {});
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gemma-3-12b" } });
    expect(screen.getAllByText("Fallback: no limits set for this model.")).toHaveLength(2);
    expect((screen.getByLabelText("Context window") as HTMLInputElement).value).toBe("32768");
    expect(screen.getByText(/^Auto · /)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Context tokens"), { target: { value: "40000" } });
    expect(screen.getByText("40,000 → 32,000 (model window)")).toBeTruthy();
  });

  it("counts the changes on the closed Model toggle", async () => {
    await openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Model" }));
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gemma-3-12b" } });
    fireEvent.click(screen.getByRole("button", { name: /^Model/ }));
    expect(screen.getByRole("button", { name: /^Model/ }).textContent).toBe("Model· 1 changed");
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
