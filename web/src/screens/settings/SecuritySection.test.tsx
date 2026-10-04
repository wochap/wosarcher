import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

describe("SecuritySection", () => {
  it("shows the session and signs out", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    expect(
      await screen.findByText(/^Signed in on this browser since Oct 3, \d\d:\d\d\.$/),
    ).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    });
    expect(callsTo(api, "logout")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();
  });

  it("says no password is set and has no Sign out when the method is none", async () => {
    const api = fakeApi();
    api.data.session = { method: "none", since: null, expires: null, token_name: null };
    renderApp({ hash: "#/settings", api });
    expect(
      await screen.findByText("No password is set; the server accepts local connections only."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("lists masked tokens and shows a created token once", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    expect(await screen.findByText("wosarcher_••••k9Qz")).toBeTruthy();
    expect(screen.getByText("Never")).toBeTruthy();
    const create = screen.getByRole("button", { name: "Create token" }) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Token name"), { target: { value: "ci-runner-2" } });
    await act(async () => {
      fireEvent.click(create);
    });
    expect(screen.getByText("Token “ci-runner-2” created")).toBeTruthy();
    const full = screen.getByText(/^wosarcher_x{32}/);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
    expect(screen.getByText("Copy it now. It won't be shown again.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(full.isConnected).toBe(false);
    expect(screen.queryByText(/^wosarcher_x{32}/)).toBeNull();
  });

  it("has the API tokens help", async () => {
    renderApp({ hash: "#/settings" });
    expect(await screen.findByRole("button", { name: "Help: API tokens" })).toBeTruthy();
  });

  it("shows the empty text without tokens", async () => {
    renderApp({ hash: "#/settings", api: fakeApi({ tokens: [] }) });
    expect(
      await screen.findByText(
        "No tokens. The local API only accepts requests from a signed-in browser.",
      ),
    ).toBeTruthy();
  });

  it("sends nothing when the revoke is cancelled or escaped", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const row = (await screen.findByText("ci-runner")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    expect(screen.getByRole("alertdialog", { name: "Revoke “ci-runner”?" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(callsTo(api, "deleteToken")).toHaveLength(0);
    expect(screen.getByText("ci-runner")).toBeTruthy();
  });

  it("revokes after confirmation, removes the row, and shows a toast", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const row = (await screen.findByText("ci-runner")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Revoke token" }));
    });
    expect(callsTo(api, "deleteToken")).toEqual([["t2"]]);
    expect(screen.queryByText("ci-runner")).toBeNull();
    expect(screen.getByText("Token “ci-runner” revoked")).toBeTruthy();
  });
});
