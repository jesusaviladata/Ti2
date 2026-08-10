"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDialog } from "@/hooks/useDialog";

interface Props {
  open:          boolean;
  title:         string;
  message:       string;
  confirmLabel?: string;
  cancelLabel?:  string;
  danger?:       boolean;
  onConfirm:     () => void;
  onCancel:      () => void;
}

/**
 * Diálogo de confirmación reutilizable y accesible (C-15) — reemplaza el `confirm()`
 * nativo del navegador. Cierra con Escape, atrapa el foco y respeta el design system.
 */
export function ConfirmDialog({
  open, title, message,
  confirmLabel = "Confirmar",
  cancelLabel  = "Cancelar",
  danger = false,
  onConfirm, onCancel,
}: Props) {
  const dialogRef = useDialog(open, onCancel);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={onCancel} aria-hidden="true" />

      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        className="relative z-10 w-full max-w-sm rounded-[1.25rem] bg-carbon border border-musgo/30 shadow-2xl p-6"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className={`w-9 h-9 rounded-[0.65rem] flex items-center justify-center shrink-0 ${
            danger ? "bg-red-900/20" : "bg-musgo/30"
          }`}>
            <AlertTriangle size={16} className={danger ? "text-red-400/80" : "text-arcilla/80"} />
          </div>
          <div className="min-w-0">
            <h2 id="confirm-title" className="font-sans text-base font-medium text-crema/90">{title}</h2>
            <p id="confirm-message" className="font-mono text-xs text-crema/45 mt-1 leading-relaxed">{message}</p>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button variant="outline" type="button" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            className={danger ? "bg-red-900/40 border border-red-800/50 text-red-200 hover:bg-red-900/60" : ""}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
