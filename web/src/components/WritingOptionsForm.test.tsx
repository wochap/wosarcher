import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { WritingOptions } from "../api/types";
import { writing } from "../test/fixtures/data";
import { WritingOptionsForm } from "./WritingOptionsForm";

function Harness({ start, base }: { start: WritingOptions; base?: WritingOptions }) {
  const [value, setValue] = useState(start);
  return (
    <WritingOptionsForm
      idPrefix="t"
      value={value}
      base={base}
      mark="overridden"
      onChange={(field, v) => setValue((w) => ({ ...w, [field]: v }))}
    />
  );
}

describe("WritingOptionsForm", () => {
  it("marks a changed field with its base value, and Reset restores it", () => {
    render(<Harness start={writing} base={writing} />);
    expect(screen.queryByText("overridden")).toBeNull();
    fireEvent.click(screen.getByLabelText("Critical"));
    expect(screen.getByText("overridden")).toBeTruthy();
    expect(screen.getByText("default: Analytical")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.queryByText("overridden")).toBeNull();
    expect((screen.getByLabelText("Analytical") as HTMLInputElement).checked).toBe(true);
  });

  it("commits the length on blur, not per keystroke", () => {
    render(<Harness start={writing} base={writing} />);
    const words = screen.getByLabelText("Target length");
    fireEvent.change(words, { target: { value: "800" } });
    expect(screen.queryByText("overridden")).toBeNull();
    fireEvent.blur(words);
    expect(screen.getByText("default: 1200 words")).toBeTruthy();
  });

  it("lists unlisted tone and language values as options", () => {
    render(<Harness start={{ ...writing, tone: "whimsical", language: "klingon" }} />);
    expect((screen.getByLabelText("Whimsical") as HTMLInputElement).checked).toBe(true);
    const language = screen.getByLabelText("Language") as HTMLSelectElement;
    expect(language.value).toBe("klingon");
  });
});
