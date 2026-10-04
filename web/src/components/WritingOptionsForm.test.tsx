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
    const tone = screen.getByLabelText("Tone") as HTMLSelectElement;
    fireEvent.change(tone, { target: { value: "critical" } });
    expect(screen.getByText("overridden")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Overridden" })).toBeTruthy();
    expect(screen.getByText("default: Analytical")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.queryByText("overridden")).toBeNull();
    expect(tone.value).toBe("analytical");
  });

  it("commits the length on blur, not per keystroke", () => {
    render(<Harness start={writing} base={writing} />);
    const words = screen.getByLabelText("Length (words)");
    fireEvent.change(words, { target: { value: "800" } });
    expect(screen.queryByText("overridden")).toBeNull();
    fireEvent.blur(words);
    expect(screen.getByText("default: 1200 words")).toBeTruthy();
  });

  it("lists unlisted tone and language values as options", () => {
    render(<Harness start={{ ...writing, tone: "whimsical", language: "klingon" }} />);
    const tone = screen.getByLabelText("Tone") as HTMLSelectElement;
    expect(tone.value).toBe("whimsical");
    expect(tone.selectedOptions[0].textContent).toBe("whimsical");
    const language = screen.getByLabelText("Language") as HTMLSelectElement;
    expect(language.value).toBe("klingon");
  });

  it("offers the tones with their descriptions and reference styles as segments", () => {
    render(<Harness start={{ ...writing, tone: "objective" }} />);
    const tone = screen.getByLabelText("Tone") as HTMLSelectElement;
    expect(tone.selectedOptions[0].textContent).toBe("Objective — neutral and evidence-first");
    expect(tone.options).toHaveLength(11);
    fireEvent.click(screen.getByLabelText("MLA"));
    expect((screen.getByLabelText("MLA") as HTMLInputElement).checked).toBe(true);
  });

  it("puts a help button after each label", () => {
    render(<Harness start={writing} />);
    for (const label of [
      "Tone",
      "Custom instructions",
      "Length (words)",
      "Language",
      "Citation marker",
      "Reference style",
    ])
      expect(screen.getByRole("button", { name: `Help: ${label}` })).toBeTruthy();
  });

  it("shortens long custom instructions in the base text", () => {
    const base = { ...writing, tone_instructions: "Assume the reader knows CUDA well." };
    render(<Harness start={{ ...base, tone_instructions: "" }} base={base} />);
    expect(screen.getByText("default: “Assume the reader knows CUDA…”")).toBeTruthy();
  });
});
