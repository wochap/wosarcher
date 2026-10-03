import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { type Ui, UiContext } from "../app/context";
import { handleKey, type Overlay } from "../app/keys";
import { Dialog } from "./Dialog";

function setup(role: "dialog" | "alertdialog") {
  const open: Overlay[] = [];
  const ui = {
    overlay: (kind, close) => {
      const entry = { kind, close };
      open.push(entry);
      return () => open.splice(open.indexOf(entry), 1);
    },
  } as Partial<Ui> as Ui;
  const onClose = vi.fn();
  render(
    <UiContext.Provider value={ui}>
      <Dialog role={role} title="Revoke “ci”?" onClose={onClose}>
        <p>body</p>
      </Dialog>
    </UiContext.Provider>,
  );
  const pressEscape = () =>
    handleKey(new KeyboardEvent("keydown", { key: "Escape" }), {
      locked: false,
      screen: "settings",
      goTo: () => {},
      overlays: () => open,
    });
  return { onClose, pressEscape };
}

describe("Dialog", () => {
  it("renders a modal alert dialog that only Escape closes", () => {
    const { onClose, pressEscape } = setup("alertdialog");
    const dialog = screen.getByRole("alertdialog", { name: "Revoke “ci”?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    fireEvent.click(dialog.parentElement as HTMLElement);
    expect(onClose).not.toHaveBeenCalled();
    pressEscape();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("closes a form dialog on a backdrop click but not on a click inside", () => {
    const { onClose } = setup("dialog");
    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(dialog.parentElement as HTMLElement);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
