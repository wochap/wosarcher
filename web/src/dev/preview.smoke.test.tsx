import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Preview } from "./preview";

const SCENARIOS: [string, RegExp][] = [
  ["new", /New research run/],
  ["empty", /No run in progress/],
  ["live", /^Running$/],
  ["loading", /^Connecting to ws:/],
  ["queued", /^Waiting for a free slot: 2 of 2 in use \(1 web, 1 CLI\)/],
  ["queued-cli", /all by CLI runs an agent started on this machine/],
  ["live-cli", /^cli$/],
  ["cancel-cli", /^Cancel this CLI run\?$/],
  ["live-api", /^api · ci-runner$/],
  ["reconnecting", /Connection lost\. Reconnecting \(attempt 1\)/],
  ["failure", /Run failed at Score/],
  ["cancelled", /^Cancelled at Fetch after/],
  ["finished", /^Recommendations$/],
  ["versions", /^Rewritten from r_8c21/],
  ["source", /^Chunk 1 of 5$/],
  ["source-loading", /^Loading cleaned text…$/],
  ["source-truncated", /^Fetch stopped here$/],
  ["source-file", /^Attached file · no URL$/],
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
