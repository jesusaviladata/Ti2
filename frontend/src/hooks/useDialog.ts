"use client";

import { useEffect, useRef } from "react";

/**
 * Accesibilidad de modales (C-21): al abrir, mueve el foco dentro del diálogo,
 * atrapa el Tab dentro de él, cierra con Escape y devuelve el foco al elemento previo
 * al cerrar. Devuelve un ref para el contenedor del diálogo.
 *
 * IMPORTANTE: el efecto depende SOLO de `open`. `onClose` se guarda en un ref para que
 * un cambio de su identidad en cada render (callback no memoizado) NO re-ejecute el
 * efecto — antes eso re-enfocaba el primer elemento (el botón X) en cada tecla, robando
 * el foco a los inputs al escribir.
 */
export function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;   // siempre la última versión, sin disparar el efecto

  useEffect(() => {
    if (!open) return;
    const node = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const getFocusables = () =>
      node
        ? Array.from(
            node.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
          )
        : [];

    // Al abrir, enfocar el primer CAMPO (input/textarea/select) si existe; si no, el
    // primer enfocable. Así el cursor cae en el primer campo, no en el botón Cerrar.
    const focusables = getFocusables();
    const firstField = focusables.find((el) =>
      ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)
    );
    (firstField ?? focusables[0])?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key === "Tab") {
        const items = getFocusables();
        if (items.length === 0) return;
        const active = document.activeElement as HTMLElement;
        const idx = items.indexOf(active);
        if (e.shiftKey && idx <= 0) {
          e.preventDefault();
          items[items.length - 1].focus();
        } else if (!e.shiftKey && idx === items.length - 1) {
          e.preventDefault();
          items[0].focus();
        }
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  return ref;
}
