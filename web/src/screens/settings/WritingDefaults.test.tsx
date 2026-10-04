import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { ServerSettings } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

describe("WritingDefaults", () => {
  it("saves a changed length once, on blur, and shows Saved", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const words = await screen.findByLabelText<HTMLInputElement>("Length (words)");
    // The input renders before the saved settings arrive; edit only after they load.
    await waitFor(() => expect(words.value).toBe("1200"));
    fireEvent.change(words, { target: { value: "800" } });
    expect(callsTo(api, "putSettings")).toHaveLength(0);
    await act(async () => {
      fireEvent.blur(words);
    });
    const puts = callsTo(api, "putSettings") as [ServerSettings][];
    expect(puts).toHaveLength(1);
    expect(puts[0][0].writing.words).toBe(800);
    expect(puts[0][0].sources).toBe("both");
    expect(screen.getByText("Saved")).toBeTruthy();
  });

  it("has the Writing defaults help", async () => {
    renderApp({ hash: "#/settings" });
    expect(await screen.findByRole("button", { name: "Help: Writing defaults" })).toBeTruthy();
  });

  it("saves a tone at once", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await act(async () => {
      fireEvent.change(await screen.findByLabelText("Tone"), { target: { value: "critical" } });
    });
    expect((callsTo(api, "putSettings")[0][0] as ServerSettings).writing.tone).toBe("critical");
  });

  it("sends a reference style picked in the segments", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    await act(async () => {
      fireEvent.click(await screen.findByLabelText("MLA"));
    });
    const puts = callsTo(api, "putSettings") as [ServerSettings][];
    expect(puts[0][0].writing.reference_style).toBe("MLA");
  });

  it("shows the server's error and restores the earlier value", async () => {
    const api = fakeApi();
    api.putSettings = async () => {
      throw new ApiError(422, "invalid_request", "x", { "writing.language": "unknown language" });
    };
    renderApp({ hash: "#/settings", api });
    const language = (await screen.findByLabelText("Language")) as HTMLSelectElement;
    await act(async () => {
      fireEvent.change(language, { target: { value: "german" } });
    });
    expect(screen.getByText("unknown language")).toBeTruthy();
    expect(language.value).toBe("english");
  });
});
