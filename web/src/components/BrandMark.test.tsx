import { render } from "@testing-library/react";
import { BrandMark } from "./BrandMark";

describe("BrandMark", () => {
  it.each([
    [16, "3.4", "2.6"],
    [18, "3", "2.4"],
    [22, "3", "2.4"],
    [28, "2.6", "2"],
    [72, "2.4", "2"],
  ])("size %i draws stroke %s and dot %s", (size, stroke, dot) => {
    const { container } = render(<BrandMark size={size} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe(String(size));
    expect(svg?.getAttribute("stroke-width")).toBe(stroke);
    expect(container.querySelector("circle")?.getAttribute("r")).toBe(dot);
  });
});
