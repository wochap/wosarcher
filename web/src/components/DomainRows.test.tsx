import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { DomainLists } from "../api/types";
import { renderWithHelp } from "../test/help";
import { DomainRows } from "./DomainRows";

function Rows({ initial }: { initial: DomainLists }) {
  const [lists, setLists] = useState(initial);
  return (
    <DomainRows
      idPrefix="t"
      lists={lists}
      onChange={(kind, list) => setLists((l) => ({ ...l, [kind]: list ?? [] }))}
    />
  );
}

const chips = (label: string) =>
  screen
    .getAllByRole("button", { name: /^Remove / })
    .map((b) => b.getAttribute("aria-label"))
    .filter((name) => name?.includes(label));

describe("DomainRows", () => {
  it("removes the last chip on Backspace in the empty input", () => {
    renderWithHelp(<Rows initial={{ allow: ["gob.pe", "sunat.gob.pe"], block: [] }} />);
    fireEvent.keyDown(screen.getByLabelText("Allow domains"), { key: "Backspace" });
    expect(screen.queryByRole("button", { name: "Remove sunat.gob.pe" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remove gob.pe" })).toBeTruthy();
  });

  it("adds typed entries on a space, lowercased and without a trailing dot", () => {
    renderWithHelp(<Rows initial={{ allow: [], block: [] }} />);
    const input = screen.getByLabelText("Allow domains");
    expect(input.getAttribute("placeholder")).toBe("any domain");
    expect(screen.getByLabelText("Block domains").getAttribute("placeholder")).toBe("none");
    fireEvent.change(input, { target: { value: "GOB.pe. pj.gob.pe" } });
    expect(chips(".")).toEqual(["Remove gob.pe", "Remove pj.gob.pe"]);
  });

  it("shows the Allow help", () => {
    renderWithHelp(<Rows initial={{ allow: [], block: [] }} />);
    fireEvent.focus(screen.getByRole("button", { name: "Help: Allow domains" }));
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toContain("Allow domains");
    expect(tooltip.textContent).toContain(
      "Only search results from these domains and their subdomains are used. Empty allows every domain. Your files are never filtered.",
    );
  });
});
