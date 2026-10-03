// Nocturne dialog: `.dialog-backdrop` and `.dialog`. Escape closes it through the overlay
// stack; a backdrop click closes form dialogs only, never confirmations.
import { type ReactNode, useEffect, useId, useRef } from "react";
import { useUi } from "../app/context";
import css from "./Dialog.module.css";

type Props = {
  title: ReactNode;
  /** `alertdialog` for confirmations, `dialog` for forms. */
  role?: "dialog" | "alertdialog";
  onClose: () => void;
  className?: string;
  children: ReactNode;
};

export function Dialog({ title, role = "dialog", onClose, className, children }: Props) {
  const { overlay } = useUi();
  const titleId = useId();
  const backdrop = useRef<HTMLDivElement>(null);
  useEffect(() => overlay(role, onClose), [overlay, role, onClose]);
  useEffect(() => {
    const element = backdrop.current;
    if (!element || role !== "dialog") return;
    const onClick = (e: MouseEvent) => e.target === element && onClose();
    element.addEventListener("click", onClick);
    return () => element.removeEventListener("click", onClick);
  }, [role, onClose]);
  const content = (
    <>
      <div id={titleId} className="dialog-title">
        {title}
      </div>
      {children}
    </>
  );
  return (
    <div ref={backdrop} className={`dialog-backdrop ${css.backdrop}`}>
      {role === "alertdialog" ? (
        <div
          className={`dialog ${className ?? ""}`}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={titleId}
        >
          {content}
        </div>
      ) : (
        <div
          className={`dialog ${className ?? ""}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
        >
          {content}
        </div>
      )}
    </div>
  );
}
