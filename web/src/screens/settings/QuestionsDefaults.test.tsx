import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ServerSettings } from "../../api/types";
import { HELP } from "../../components/help";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function open(api = fakeApi()) {
  renderApp({ hash: "#/settings", api });
  const timeout = await screen.findByLabelText<HTMLInputElement>("Timeout when idle");
  await waitFor(() => expect(timeout.value).toBe("60"));
  return { api, timeout };
}

const puts = (api: ReturnType<typeof fakeApi>) => callsTo(api, "putSettings") as [ServerSettings][];

describe("Run questions settings", () => {
  it("shows the toggles and the timeout from the settings", async () => {
    await open();
    expect(screen.getByRole("heading", { name: "Run questions" })).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>("switch", { name: "Ask before searching" }).ariaChecked,
    ).toBe("true");
    expect(
      screen.getByRole<HTMLButtonElement>("switch", { name: "Ask between rounds" }).ariaChecked,
    ).toBe("true");
    expect(screen.getByText("· counts down only while you are away")).toBeTruthy();
  });

  it("saves rounds off with the whole settings object and shows Saved", async () => {
    const { api } = await open();
    await act(async () => {
      fireEvent.click(screen.getByRole("switch", { name: "Ask between rounds" }));
    });
    expect(puts(api)).toHaveLength(1);
    expect(puts(api)[0][0].questions).toEqual({
      clarify: true,
      rounds: false,
      timeout: 60,
      max_wait: 1800,
    });
    expect(puts(api)[0][0].writing.words).toBe(1200);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
  });

  it("saves a timeout in range", async () => {
    const { api, timeout } = await open();
    await act(async () => {
      fireEvent.change(timeout, { target: { value: "0" } });
    });
    expect(puts(api)[0][0].questions.timeout).toBe(0);
    expect(screen.getByText("· 0 continues at once")).toBeTruthy();
  });

  it("sends nothing for a timeout outside 0 to 3600", async () => {
    const { api, timeout } = await open();
    for (const value of ["4000", "-5", "1.5", ""]) {
      await act(async () => {
        fireEvent.change(timeout, { target: { value } });
      });
    }
    expect(puts(api)).toHaveLength(0);
    expect(timeout.getAttribute("aria-invalid")).toBe("true");
  });

  it("has the verbatim help texts", async () => {
    await open();
    for (const [name, key] of [
      ["Ask before searching", "q-clarify"],
      ["Ask between rounds", "q-rounds"],
      ["Timeout when idle", "q-timeout"],
    ] as const) {
      fireEvent.mouseEnter(screen.getByRole("button", { name: `Help: ${name}` }));
      expect(screen.getByRole("tooltip").textContent).toContain(HELP[key].body);
      fireEvent.mouseLeave(screen.getByRole("button", { name: `Help: ${name}` }));
    }
    expect(HELP["q-timeout"].body).toBe(
      "The run waits while you are here. When you are away, it counts down and then continues with the recommended answers. Set the default in Settings; override it per run in Options.",
    );
  });
});
