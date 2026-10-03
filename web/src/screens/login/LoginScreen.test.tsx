import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { FakeApi } from "../../test/fakeApi";
import { fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

/** The app starts locked: the session check answers 401 until a login succeeds. */
function lockedApp(api: FakeApi = fakeApi(), hash = "#/history") {
  let signedIn = false;
  const login = api.login.bind(api);
  return renderApp({
    hash,
    api,
    wrap: (fake, unauthorized) => ({
      ...fake,
      getSession: async () => {
        if (signedIn) return fake.data.session;
        unauthorized();
        throw new ApiError(401, "unauthenticated", "sign in");
      },
      login: async (password) => {
        const result = await login(password);
        signedIn = result.kind === "ok";
        return result;
      },
    }),
  });
}

const field = () => screen.getByLabelText("Password") as HTMLInputElement;
const submit = () => screen.getByRole("button", { name: /Sign in|Try again/ }) as HTMLButtonElement;

async function enter(password: string) {
  fireEvent.change(field(), { target: { value: password } });
  await act(async () => {
    fireEvent.submit(field().form as HTMLFormElement);
  });
}

afterEach(() => vi.useRealTimers());

describe("LoginScreen", () => {
  it("shows the sign-in screen, disables Sign in while empty, and unlocks on success", async () => {
    lockedApp();
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();
    expect(screen.getByText("Enter the password for this wosarcher instance.")).toBeTruthy();
    expect(submit().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field().type).toBe("text");
    await enter("secret");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Sign in" })).toBeNull());
  });

  it("returns to the same screen after the session expires", async () => {
    const api = fakeApi();
    let expired = true;
    renderApp({
      hash: "#/history",
      api,
      wrap: (fake, unauthorized) => ({
        ...fake,
        listRuns: async () => {
          if (expired) {
            unauthorized();
            throw new ApiError(401, "unauthenticated", "sign in");
          }
          return fake.listRuns();
        },
        login: async (password) => {
          expired = false;
          return fake.login(password);
        },
      }),
    });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();
    await enter("secret");
    expect(await screen.findByRole("heading", { name: "Run history" })).toBeTruthy();
    expect(window.location.hash).toBe("#/history");
  });

  it("shows attempts left after a wrong password, empties and refocuses the field", async () => {
    lockedApp(fakeApi({ logins: [{ kind: "wrong", attemptsLeft: 3 }] }));
    await screen.findByRole("heading", { name: "Sign in" });
    await enter("nope");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Wrong password");
    expect(alert.textContent).toContain("3 attempts left before sign-in pauses.");
    expect(field().getAttribute("aria-invalid")).toBe("true");
    expect(field().value).toBe("");
    expect(document.activeElement).toBe(field());
  });

  it("pauses sign-in with a countdown, then allows it again", async () => {
    lockedApp(fakeApi({ logins: [{ kind: "limited", retryAfter: 30 }] }));
    await screen.findByRole("heading", { name: "Sign in" });
    vi.useFakeTimers({ shouldAdvanceTime: false });
    await enter("x");
    expect(submit().textContent).toBe("Try again in 30 s");
    expect(screen.getByRole("alert").textContent).toContain("Try again in 0:30.");
    expect(field().disabled).toBe(true);
    await act(async () => vi.advanceTimersByTime(1000));
    expect(submit().textContent).toBe("Try again in 29 s");
    await act(async () => vi.advanceTimersByTime(29_000));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(field().disabled).toBe(false);
    expect(submit().textContent).toBe("Sign in");
  });
});
