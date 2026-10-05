// The prototype's toast: one at a time, 2.2 s, 5 s for an error, or 6 s when it offers Undo.
import { Check, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ToastOptions } from "../app/context";
import css from "./Toast.module.css";

export const TOAST_MS = 2200;
export const UNDO_MS = 6000;
export const ERROR_MS = 5000;

type Shown = { id: number; message: string; undo?: () => void; error?: boolean };

export function useToastState() {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const next = useRef(0);
  const toast = useCallback((message: string, options: ToastOptions = {}) => {
    clearTimeout(timer.current);
    const id = ++next.current;
    setShown({ id, message, undo: options.undo, error: options.error });
    const ms = options.undo ? UNDO_MS : options.error ? ERROR_MS : TOAST_MS;
    timer.current = setTimeout(() => setShown(null), ms);
  }, []);
  const dismiss = useCallback(() => {
    clearTimeout(timer.current);
    setShown(null);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return { shown, toast, dismiss };
}

export function Toast({ shown, dismiss }: { shown: Shown | null; dismiss: () => void }) {
  if (!shown) return null;
  const undo = shown.undo;
  return (
    <div role="status" className={css.toast} key={shown.id}>
      {shown.error ? (
        <WarningCircle className={css.danger} aria-hidden="true" />
      ) : (
        <Check className={css.icon} />
      )}
      {shown.message}
      {undo && (
        <button
          type="button"
          className={`btn btn-ghost ${css.undo}`}
          onClick={() => {
            undo();
            dismiss();
          }}
        >
          Undo
        </button>
      )}
    </div>
  );
}
