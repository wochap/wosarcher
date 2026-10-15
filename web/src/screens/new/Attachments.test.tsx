import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Attachments } from "./Attachments";

function Harness() {
  const [files, setFiles] = useState<File[]>([]);
  return <Attachments files={files} onChange={setFiles} />;
}

const file = (name: string, size: number) => new File(["x".repeat(size)], name);

describe("Attachments", () => {
  it("has the Attachments help", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Help: Attachments" })).toBeTruthy();
  });

  it("adds .md, .txt and .json files, skips others, ignores duplicates, and removes", () => {
    render(<Harness />);
    const zone = screen.getByRole("button", { name: "Add .md, .txt or .json files" });
    fireEvent.dragOver(zone);
    expect(zone.dataset.over).toBe("true");
    fireEvent.drop(zone, {
      dataTransfer: {
        files: [file("notes.md", 4403), file("data.json", 20), file("paper.pdf", 10)],
      },
    });
    expect(zone.dataset.over).toBe("false");
    expect(screen.getByText("notes.md")).toBeTruthy();
    expect(screen.getByText("4.3 KB")).toBeTruthy();
    expect(screen.getByText("data.json")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe(
      "Skipped paper.pdf — only .md, .txt and .json are supported.",
    );
    fireEvent.drop(zone, { dataTransfer: { files: [file("notes.md", 1), file("a.txt", 12)] } });
    expect(screen.getAllByText("notes.md")).toHaveLength(1);
    expect(screen.getByText("12 B")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove notes.md" }));
    expect(screen.queryByText("notes.md")).toBeNull();
    expect(screen.getByText("a.txt")).toBeTruthy();
  });
});

describe("Reused attachments", () => {
  it("lists a reused file with its run and removes it", () => {
    function Reused() {
      const [reused, setReused] = useState([
        { runId: "r1", runName: "RAG chunking", name: "notes.md", size: 6120 },
      ]);
      return <Attachments files={[]} reused={reused} onChange={() => {}} onReused={setReused} />;
    }
    render(<Reused />);
    expect(screen.getByText("notes.md")).toBeTruthy();
    expect(screen.getByText(/reused from/).textContent).toBe("reused from RAG chunking");
    expect(screen.getByText("6.0 KB")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove notes.md" }));
    expect(screen.queryByText("notes.md")).toBeNull();
  });
});
