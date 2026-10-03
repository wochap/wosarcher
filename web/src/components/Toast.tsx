// The prototype's toast: one at a time, 2.2 s, or 6 s when it offers Undo.
import { Check } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ToastOptions } from "../app/context";
import css from "./Toast.module.css";

export const TOAST_MS = 2200;
export const UNDO_MS = 6000;

type Shown = { id: number; message: string; undo?: () => void };

export function useToastState() {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const next = useRef(0);
  const toast = useCallback((message: string, options: ToastOptions = {}) => {
    clearTimeout(timer.current);
    const id = ++next.current;
    setShown({ id, message, undo: options.undo });
    timer.current = setTimeout(() => setShown(null), options.undo ? UNDO_MS : TOAST_MS);
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
      <Check className={css.icon} />
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
