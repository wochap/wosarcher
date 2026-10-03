import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunStatus } from "../api/types";
import { StatusTag } from "./StatusTag";

const CASES: [RunStatus, string][] = [
  ["done", "Completed"],
  ["running", "Running"],
  ["queued", "Queued"],
  ["failed", "Failed"],
  ["interrupted", "Interrupted"],
  ["cancelled", "Cancelled"],
];

describe("StatusTag", () => {
  it.each(CASES)("renders %s with its icon and label", (status, label) => {
    render(<StatusTag status={status} />);
    const tag = screen.getByText(label);
    expect(tag.dataset.state).toBe(status);
    const icon = tag.querySelector("svg");
    expect(icon).toBeTruthy();
    expect(icon?.classList.contains("spin")).toBe(status === "running" || status === "queued");
  });
});
