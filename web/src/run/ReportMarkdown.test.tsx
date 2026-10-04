import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReportMarkdown } from "./ReportMarkdown";

const show = (body: string) =>
  render(
    <ReportMarkdown
      body={body}
      marker="numeric"
      context={null}
      variant="article"
      onCite={() => {}}
      onLeave={() => {}}
    />,
  );

describe("ReportMarkdown tables", () => {
  it("renders a pipe table with one header row and three body rows", () => {
    show("| Method | Cost |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n");
    const table = screen.getByRole("table");
    expect(table.className).toBe("table");
    const [head, body] = within(table).getAllByRole("rowgroup");
    expect(within(head).getAllByRole("row")).toHaveLength(1);
    expect(within(body).getAllByRole("row")).toHaveLength(3);
  });

  it("renders a citation in a cell as a chip", () => {
    show("| Item | Price |\n|---|---|\n| Plant | $0.50–$2 [13] |\n");
    const cell = screen.getByRole("cell", { name: /\$0\.50–\$2/ });
    expect(cell.textContent).toContain("$0.50–$2");
    expect(within(cell).getByRole("button", { name: "Citation 13, show passage" })).toBeTruthy();
  });
});
