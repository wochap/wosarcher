import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/renderApp";

const tooltip = () => screen.queryByRole("tooltip");

afterEach(() => vi.useRealTimers());

describe("HelpTip", () => {
  it("opens on hover and closes 140 ms after leaving", async () => {
    renderApp({ hash: "#/new" });
    const button = await screen.findByRole("button", { name: "Help: Attachments" });
    vi.useFakeTimers();
    fireEvent.mouseEnter(button);
    expect(tooltip()?.textContent).toContain("Attachments");
    fireEvent.mouseLeave(button);
    act(() => vi.advanceTimersByTime(100));
    expect(tooltip()).toBeTruthy();
    act(() => vi.advanceTimersByTime(40));
    expect(tooltip()).toBeNull();
  });

  it("stays open while the pointer is on the tooltip", async () => {
    renderApp({ hash: "#/new" });
    const button = await screen.findByRole("button", { name: "Help: Attachments" });
    vi.useFakeTimers();
    fireEvent.mouseEnter(button);
    fireEvent.mouseLeave(button);
    fireEvent.mouseEnter(tooltip() as HTMLElement);
    act(() => vi.advanceTimersByTime(500));
    expect(tooltip()).toBeTruthy();
  });

  it("opens on focus and names the tooltip in aria-describedby", async () => {
    renderApp({ hash: "#/new" });
    const button = await screen.findByRole("button", { name: "Help: Attachments" });
    fireEvent.focus(button);
    const target = document.getElementById(button.getAttribute("aria-describedby") ?? "");
    expect(target).toBe(tooltip());
  });

  it("shows the example line", async () => {
    renderApp({ hash: "#/new" });
    fireEvent.click(await screen.findByRole("button", { name: "Help: Attachments" }));
    const shown = tooltip() as HTMLElement;
    expect(shown.textContent).toContain(
      "Markdown or text files to research alongside the web, or instead of it.",
    );
    expect(shown.textContent).toContain("Example: pdf-ingest output (.md)");
  });

  it("pins on click, ignores hover, and closes on an outside press or a second click", async () => {
    renderApp({ hash: "#/settings" });
    const button = await screen.findByRole("button", { name: "Help: Writing defaults" });
    fireEvent.click(button);
    expect(button.dataset.pinned).toBe("true");
    fireEvent.mouseLeave(button);
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Help: API tokens" }));
    expect(tooltip()?.textContent).toContain("Writing defaults");
    fireEvent.pointerDown(document.body);
    expect(tooltip()).toBeNull();
    fireEvent.click(button);
    fireEvent.click(button);
    expect(tooltip()).toBeNull();
  });

  it("pins another button in place of the first", async () => {
    renderApp({ hash: "#/settings" });
    fireEvent.click(await screen.findByRole("button", { name: "Help: Writing defaults" }));
    fireEvent.click(screen.getByRole("button", { name: "Help: API tokens" }));
    expect(screen.getAllByRole("tooltip")).toHaveLength(1);
    expect(tooltip()?.textContent).toContain("For scripts and agents on other machines.");
  });

  it("closes on scroll", async () => {
    renderApp({ hash: "#/settings" });
    fireEvent.click(await screen.findByRole("button", { name: "Help: Writing defaults" }));
    fireEvent.scroll(document.body);
    expect(tooltip()).toBeNull();
  });
});
