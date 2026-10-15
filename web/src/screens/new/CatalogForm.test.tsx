import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { RunCreate } from "../../api/types";
import { HELP } from "../../components/help";
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

  it("sends the languages in the structure and no search_language", async () => {
    const { api, brief } = await openCatalog();
    await draftIt(brief);
    fireEvent.change(screen.getByLabelText("Search language"), { target: { value: "es" } });
    fireEvent.change(screen.getByLabelText("Record language"), { target: { value: "en" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.structure?.language).toBe("es");
    expect(request.structure?.record_language).toBe("en");
    expect(request).not.toHaveProperty("search_language");
  });

  it("disables Run catalog for an invalid record language", async () => {
    const { brief } = await openCatalog();
    await draftIt(brief);
    fireEvent.change(screen.getByLabelText("Record language"), { target: { value: "spanish" } });
    expect(
      (screen.getByRole("button", { name: "Run catalog" }) as HTMLButtonElement).disabled,
    ).toBe(true);
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

  it("shows the Kind help and the segment titles", async () => {
    await openCatalog();
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Help: Kind" }));
    expect(screen.getByRole("tooltip").textContent).toContain(HELP.kind.body);
    const title = (name: string) =>
      screen.getByRole("radio", { name }).closest("label")?.getAttribute("title");
    expect(title("Research")).toBe("Cited report or answer to a question");
    expect(title("Catalog")).toBe("Structured records, one per entity, from a crawl");
  });

  it("sends the profile and Extract thinking, shared with the research form", async () => {
    const { api, brief } = await openCatalog();
    await draftIt(brief);
    fireEvent.click(screen.getByRole("radio", { name: "workstation" }));
    fireEvent.click(screen.getByRole("button", { name: /^Advanced/ }));
    expect(screen.queryByLabelText("Write thinking")).toBeNull();
    expect(screen.getByLabelText("Draft thinking")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Extract thinking"), { target: { value: "low" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.profile).toBe("workstation");
    expect(request.llm?.reasoning).toEqual({ extract: "low" });
  });

  it("keeps the profile choice when switching back to Research", async () => {
    const { brief } = await openCatalog();
    await draftIt(brief);
    fireEvent.click(screen.getByRole("radio", { name: "workstation" }));
    fireEvent.click(screen.getByRole("radio", { name: "Research" }));
    fireEvent.click(screen.getByRole("button", { name: /^Options/ }));
    expect((screen.getByRole("radio", { name: "workstation" }) as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it("hides Writing for Table and sends no writing", async () => {
    const { api, brief } = await openCatalog();
    await draftIt(brief);
    expect(screen.queryByRole("group", { name: "Writing" })).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.structure?.output ?? "table").toBe("table");
    expect(request.writing).toBeUndefined();
  });

  it("shows Writing for Report and sends the output and the length", async () => {
    const { api, brief } = await openCatalog();
    await draftIt(brief);
    const output = screen.getByRole("radiogroup", { name: "Output" });
    fireEvent.click(within(output).getByRole("radio", { name: "Report" }));
    const writing = screen.getByRole("group", { name: "Writing" });
    expect(screen.getByText(/extraction calls · 1 report$/)).toBeTruthy();
    const length = within(writing).getByLabelText("Length (words)");
    fireEvent.change(length, { target: { value: "800" } });
    fireEvent.blur(length);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run catalog" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.structure?.output).toBe("report");
    expect(request.writing).toEqual({ words: 800 });
  });

  it("shows the Output help", async () => {
    const { brief } = await openCatalog();
    await draftIt(brief);
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Help: Output" }));
    expect(screen.getByRole("tooltip").textContent).toContain(HELP["c-output"].body);
  });
});
