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
        <div className="w-12 h-12 rounded-[0.75rem] bg-musgo/20 flex items-center justify-center mb-3">
          <Package size={20} className="text-crema/20" />
        </div>
        <p className="font-sans text-sm text-crema/40">Papelera vacía</p>
        <p className="font-mono text-xs text-crema/20 mt-1">Los archivos eliminados aparecerán aquí</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between px-4 py-2.5 rounded-[0.75rem] bg-musgo/10 border border-musgo/20">
        <span className="font-mono text-xs text-crema/50">
          <span className="text-crema/80">{items.length}</span> archivo{items.length !== 1 ? "s" : ""} en papelera ·{" "}
          <span className="text-arcilla">{formatBytes(totalBytes)}</span>
        </span>
        <button
          onClick={() => setEmptyConfirm(true)}
          className="font-mono text-[10px] text-red-400/60 hover:text-red-400 transition-colors"
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
      <div className="grid grid-cols-[1fr_90px_110px_160px] gap-3 px-4 py-2 text-[10px] font-mono text-crema/25 uppercase tracking-wider border-b border-musgo/15">
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
      confirming ? "bg-red-900/10" : "hover:bg-musgo/5",
      "transition-colors"
    )}>
      <div className="min-w-0">
        <p className="font-sans text-xs text-crema/75 truncate">{item.name}</p>
        <p className="font-mono text-[10px] text-crema/25 truncate mt-0.5">{item.originalPath}</p>
      </div>

      <span className="font-mono text-xs text-crema/40">{formatBytes(item.sizeBytes)}</span>

      <span className="font-mono text-[10px] text-crema/30">
        {new Date(item.deletedAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}
      </span>

      <div className="flex items-center gap-1.5 justify-end">
        {confirming ? (
          <>
            <span className="font-mono text-[10px] text-red-400/70 mr-1">¿Confirmar?</span>
            <button
              onClick={onDelete}
              className="px-2.5 py-1 rounded-[0.5rem] bg-red-900/30 border border-red-800/40 text-red-300 font-mono text-[10px] hover:bg-red-900/50 transition-colors"
            >
              Eliminar
            </button>
            <button
              onClick={onCancel}
              className="px-2.5 py-1 rounded-[0.5rem] bg-musgo/20 border border-musgo/30 text-crema/40 font-mono text-[10px] hover:text-crema/60 transition-colors"
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              onClick={onRestore}
              title="Restaurar"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-[0.5rem] bg-musgo/20 border border-musgo/30 text-crema/40 font-mono text-[10px] hover:text-crema/70 transition-colors"
            >
              <RotateCcw size={11} /> Restaurar
            </button>
            <button
              onClick={onConfirm}
              title="Eliminar definitivamente"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-[0.5rem] bg-red-900/15 border border-red-800/25 text-red-400/60 font-mono text-[10px] hover:text-red-300 transition-colors"
            >
              <Trash2 size={11} /> Eliminar
            </button>
          </>
        )}
      </div>
    </div>
  );
}
