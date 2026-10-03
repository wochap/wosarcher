import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Preview } from "./preview";

const SCENARIOS: [string, RegExp][] = [
  ["new", /New research run/],
  ["empty", /No run in progress/],
  ["live", /^Running$/],
  ["loading", /queued, waiting for a free worker/],
  ["reconnecting", /Connection lost\. Reconnecting \(attempt 1\)/],
  ["failure", /Run failed at Score/],
  ["cancelled", /^Cancelled at Fetch after/],
  ["finished", /^Recommendations$/],
  ["versions", /^Rewritten from r_8c21/],
];

afterEach(() => vi.restoreAllMocks());

describe("dev preview run scenarios", () => {
  it.each(SCENARIOS)("renders %s without errors", async (name, text) => {
    const errors = vi.spyOn(console, "error");
    render(<Preview name={name} />);
    expect((await screen.findAllByText(text, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect(errors).not.toHaveBeenCalled();
  });
});
