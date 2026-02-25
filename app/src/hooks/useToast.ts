/**
 * useToast -- app-wide toast notification manager
 *
 * Usage:
 *   const { toasts, showToast, dismissToast } = useToast();
 *   showToast({ type: "error", title: "Connection lost" });
 */

import { useState, useCallback } from "react";
import { ToastMessage, ToastType } from "../components/Toast";

let _nextId = 1;

export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback((opts: {
    type: ToastType;
    title: string;
    message?: string;
    duration?: number;
  }) => {
    const id = `toast_${_nextId++}`;
    setToasts((prev) => [...prev, { id, ...opts }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, showToast, dismissToast };
}
