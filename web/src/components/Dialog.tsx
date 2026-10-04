// Nocturne dialog: `.dialog-backdrop` and `.dialog`. Escape closes it through the overlay
// stack; a backdrop click closes form dialogs only, never confirmations.
import { type KeyboardEvent, type ReactNode, type Ref, useEffect, useId, useRef } from "react";
import { useUi } from "../app/context";
import css from "./Dialog.module.css";

type Props = {
  /** Rendered as `.dialog-title`; omit it when `labelledBy` names a title inside `children`. */
  title?: ReactNode;
  labelledBy?: string;
  onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void;
  panelRef?: Ref<HTMLDivElement>;
  /** `alertdialog` for confirmations, `dialog` for forms. */
  role?: "dialog" | "alertdialog";
  onClose: () => void;
  className?: string;
  children: ReactNode;
};

export function Dialog(props: Props) {
  const { title, labelledBy, role = "dialog", onClose, className, children } = props;
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
      {title !== undefined && (
        <div id={titleId} className="dialog-title">
          {title}
        </div>
      )}
      {children}
    </>
  );
  const shared = {
    className: `dialog ${className ?? ""}`,
    "aria-modal": true,
    "aria-labelledby": labelledBy ?? titleId,
    ref: props.panelRef,
    onKeyDown: props.onKeyDown,
  };
  return (
    <div ref={backdrop} className={`dialog-backdrop ${css.backdrop}`}>
      {role === "alertdialog" ? (
        <div role="alertdialog" {...shared}>
          {content}
        </div>
      ) : (
        <div role="dialog" tabIndex={-1} {...shared}>
          {content}
        </div>
      )}
    </div>
  );
}
