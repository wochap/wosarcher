import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { RunCreate } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function openCatalog(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  await screen.findByLabelText("Question");
  fireEvent.click(screen.getByRole("radio", { name: "Catalog" }));
  const brief = screen.getByLabelText("Brief") as HTMLTextAreaElement;
  return { api, brief };
}

const draftIt = async (brief: HTMLTextAreaElement) => {
  fireEvent.change(brief, { target: { value: "Every public body" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Draft structure" }));
  });
};

describe("catalog form", () => {
  it("shows Draft structure and Run catalog, and hides Options", async () => {
    const { brief } = await openCatalog();
    expect(screen.getByRole("heading", { name: "New catalog run" })).toBeTruthy();
    expect(brief.placeholder).toMatch(/^e\.g\. Every public organization/);
    expect(screen.queryByText("Options")).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Draft structure" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Run catalog" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("drafts the structure, edits a limit, and posts the catalog run", async () => {
    const { api, brief } = await openCatalog();
    await draftIt(brief);
    expect(callsTo(api, "draftStructure")[0][0]).toMatchObject({ brief: "Every public body" });
    expect(
      screen.getByText("Up to 200 nodes · about 400 pages · 200 extraction calls"),
    ).toBeTruthy();
    expect(screen.getByText("Poder Legislativo")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Max nodes"), { target: { value: "50" } });
    expect(screen.getByText("Up to 50 nodes · about 100 pages · 50 extraction calls")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Field 1 name"), { target: { value: "the id" } });
    expect((screen.getByLabelText("Field 1 name") as HTMLInputElement).value).toBe("the_id");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.kind).toBe("catalog");
    expect(request.query).toBe("Every public body");
    expect(request.structure?.limits?.max_nodes).toBe(50);
    expect(request.structure?.fields[0].name).toBe("the_id");
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("shows a failed draft and a rejected structure with Fix in Structure", async () => {
    const api = fakeApi();
    const drafted = api.data.draft;
    api.data.draft = new ApiError(502, "draft_failed", "the model replied badly");
    const { brief } = await openCatalog(api);
    await draftIt(brief);
    expect(screen.getByText("Couldn’t draft the structure")).toBeTruthy();
    api.data.draft = drafted;
    await draftIt(brief);
    api.createRun = async () => {
      throw new ApiError(422, "invalid", "structure.seeds: seed type not in the enum", {
        "structure.seeds": "seed type not in the enum",
      });
    };
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    fireEvent.click(screen.getByRole("button", { name: "Fix in Structure" }));
    expect(document.activeElement?.closest('[data-row="c-seeds"]')).toBeTruthy();
  });

  it("keeps the kind and brief across screens", async () => {
    const { brief } = await openCatalog();
    fireEvent.change(brief, { target: { value: "Kept brief" } });
    await act(async () => {
      window.location.hash = "#/history";
    });
    await act(async () => {
      window.location.hash = "#/new";
    });
    expect(((await screen.findByLabelText("Brief")) as HTMLTextAreaElement).value).toBe(
      "Kept brief",
    );
  });
});
