"use client";

import { useState } from "react";
import { Trash2, RotateCcw, AlertTriangle, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useTrash, usePermanentDelete, useRestore } from "@/hooks/useCleanup";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { TrashItem } from "@/types/cleanup";

export function TrashPanel() {
  const { data } = useTrash();
  const permDelete = usePermanentDelete();
  const restore    = useRestore();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [emptyConfirm, setEmptyConfirm] = useState(false);

  const items = data?.items ?? [];
  const totalBytes = items.reduce((s, i) => s + i.sizeBytes, 0);

  if (!items.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-[0.75rem] bg-surface flex items-center justify-center mb-3">
          <Package size={20} className="text-subtle" />
        </div>
        <p className="font-sans text-sm text-muted">Papelera vacía</p>
        <p className="font-sans text-xs text-subtle mt-1">Los archivos eliminados aparecerán aquí</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between px-4 py-2.5 rounded-[0.75rem] bg-surface border border-musgo/20">
        <span className="font-sans text-xs text-muted">
          <span className="text-crema">{items.length}</span> archivo{items.length !== 1 ? "s" : ""} en papelera ·{" "}
          <span className="text-arcilla">{formatBytes(totalBytes)}</span>
        </span>
        <button
          onClick={() => setEmptyConfirm(true)}
          className="font-sans text-xs text-danger hover:text-danger transition-colors"
        >
          Vaciar papelera
        </button>
      </div>

      <ConfirmDialog
        open={emptyConfirm}
        danger
        title="Vaciar papelera"
        message={`Se eliminarán permanentemente ${items.length} archivo${items.length !== 1 ? "s" : ""}. Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar todo"
        onConfirm={() => { items.forEach((i) => permDelete.mutate(i.id)); setEmptyConfirm(false); }}
        onCancel={() => setEmptyConfirm(false)}
      />

      {/* Table header */}
      <div className="grid grid-cols-[1fr_90px_110px_160px] gap-3 px-4 py-2 text-xs font-sans text-subtle uppercase tracking-wider border-b border-musgo/15">
        <span>Archivo</span>
        <span>Tamaño</span>
        <span>Eliminado</span>
        <span />
      </div>

      <div className="divide-y divide-musgo/10">
        {items.map((item) => (
          <TrashRow
            key={item.id}
            item={item}
            confirming={confirming === item.id}
            onConfirm={() => setConfirming(item.id)}
            onCancel={() => setConfirming(null)}
            onDelete={() => { permDelete.mutate(item.id); setConfirming(null); }}
            onRestore={() => restore.mutate(item.id)}
          />
        ))}
      </div>
    </div>
  );
}

function TrashRow({
  item, confirming, onConfirm, onCancel, onDelete, onRestore,
}: {
  item:       TrashItem;
  confirming: boolean;
  onConfirm:  () => void;
  onCancel:   () => void;
  onDelete:   () => void;
  onRestore:  () => void;
}) {
  return (
    <div className={cn(
      "grid grid-cols-[1fr_90px_110px_160px] gap-3 px-4 py-3.5 items-center",
      confirming ? "bg-danger/10" : "hover:bg-musgo/5",
      "transition-colors"
    )}>
      <div className="min-w-0">
        <p className="font-sans text-xs text-crema truncate">{item.name}</p>
        <p className="font-sans text-xs text-subtle truncate mt-0.5">{item.originalPath}</p>
      </div>

      <span className="font-sans text-xs text-muted">{formatBytes(item.sizeBytes)}</span>

      <span className="font-sans text-xs text-subtle">
        {new Date(item.deletedAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}
      </span>

      <div className="flex items-center gap-1.5 justify-end">
        {confirming ? (
          <>
            <span className="font-sans text-xs text-danger mr-1">¿Confirmar?</span>
            <button
              onClick={onDelete}
              className="px-2.5 py-1 rounded-[0.5rem] bg-red-900/30 border border-red-800/40 text-danger font-sans text-xs hover:bg-red-900/50 transition-colors"
            >
              Eliminar
            </button>
            <button
              onClick={onCancel}
              className="px-2.5 py-1 rounded-[0.5rem] bg-surface border border-musgo/30 text-muted font-sans text-xs hover:text-muted transition-colors"
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              onClick={onRestore}
              title="Restaurar"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-[0.5rem] bg-surface border border-musgo/30 text-muted font-sans text-xs hover:text-crema transition-colors"
            >
              <RotateCcw size={11} /> Restaurar
            </button>
            <button
              onClick={onConfirm}
              title="Eliminar definitivamente"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-[0.5rem] bg-danger/10 border border-red-800/25 text-danger font-sans text-xs hover:text-danger transition-colors"
            >
              <Trash2 size={11} /> Eliminar
            </button>
          </>
        )}
      </div>
    </div>
  );
}
