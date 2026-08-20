"use client";

import { useState, useCallback } from "react";
import { ShieldCheck, RefreshCw, Trash2 } from "lucide-react";
import { BackupStatusBadge } from "./backup-status-badge";
import { useBackupList, useRetryBackupDelivery } from "@/hooks/useBackups";
import { formatBytes, formatDuration } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { ContextMenuPortal } from "@/components/ui/context-menu-portal";

interface CtxState { x: number; y: number; id: string }

export function BackupList() {
  const [page, setPage] = useState(0);
  const limit = 20;
  const { data, isLoading, isFetching } = useBackupList(page * limit, limit);
  const queryClient = useQueryClient();
  const [ctx, setCtx] = useState<CtxState | null>(null);
  const retryDelivery = useRetryBackupDelivery();

  const handleContextMenu = useCallback((e: React.MouseEvent, id: string) => {
    e.preventDefault();
    setCtx({ x: e.clientX, y: e.clientY, id });
  }, []);

  async function deleteBackup(id: string) {
    await api.delete(`/api/v1/backups/${id}`);
    queryClient.invalidateQueries({ queryKey: ["backups"] });
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 rounded-[0.75rem] bg-musgo/10 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data?.items.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="w-12 h-12 rounded-[0.75rem] bg-musgo/20 flex items-center justify-center mb-3">
          <ShieldCheck size={22} className="text-crema/20" />
        </div>
        <p className="font-sans text-sm text-crema/40">Sin backups registrados</p>
        <p className="font-mono text-xs text-crema/20 mt-1">Crea el primero con el botón "Nuevo Backup"</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      {/* Table header */}
      <div className="grid min-w-[860px] grid-cols-[minmax(180px,1fr)_85px_110px_125px_80px_110px_70px] gap-3 px-4 py-2 text-[10px] font-mono text-crema/30 uppercase tracking-wider border-b border-musgo/15">
        <span>Base de datos</span>
        <span>Tipo</span>
        <span>Estado</span>
        <span>ZIP / envío</span>
        <span>Tamaño</span>
        <span>Inicio</span>
        <span>Duración</span>
      </div>

      <div className="divide-y divide-musgo/10">
        {data.items.map((b) => (
          <div
            key={b.id}
            onContextMenu={(e) => handleContextMenu(e, b.id)}
            className={cn(
              "grid min-w-[860px] grid-cols-[minmax(180px,1fr)_85px_110px_125px_80px_110px_70px] gap-3 px-4 py-3.5 items-center",
              "hover:bg-musgo/5 transition-colors cursor-context-menu select-none"
            )}
          >
            <div>
              <p className="font-sans text-sm text-crema/80 truncate">{b.databaseName}</p>
              {b.triggerReason === "full_initial_required" ? <p className="mt-0.5 text-[10px] text-amber-400/80">Full inicial requerido</p> : null}
              {b.errorMessage && (
                <p className="font-mono text-[10px] text-red-400/70 truncate mt-0.5">{b.errorMessage}</p>
              )}
            </div>
            <span className="font-mono text-xs text-crema/40 capitalize">{b.backupType}</span>
            <BackupStatusBadge status={b.status} />
            <DeliveryStatus status={b.deliveryStatus} phase={b.deliveryPhase} error={b.deliveryErrorMessage} onRetry={b.deliveryStatus === "failed" ? () => retryDelivery.mutate(b.id) : undefined} />
            <span className="text-xs tabular-nums text-crema/40">
              {b.fileSizeBytes ? formatBytes(b.fileSizeBytes) : "—"}
            </span>
            <span className="text-xs tabular-nums text-crema/30">
              {b.startedAt
                ? new Date(b.startedAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })
                : "—"}
            </span>
            <span className="text-xs tabular-nums text-crema/30">
              {b.durationSecs != null ? formatDuration(Math.ceil(b.durationSecs / 60)) : "—"}
            </span>
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-musgo/15">
        <span className="font-mono text-xs text-crema/25">
          {data.total} backup{data.total !== 1 ? "s" : ""} en total
          {isFetching && <RefreshCw size={10} className="inline ml-2 animate-spin" />}
        </span>
        <div className="flex gap-2">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}
            className="font-mono text-xs text-crema/30 hover:text-crema disabled:opacity-20 transition-colors px-2">
            ← Anterior
          </button>
          <button disabled={(page + 1) * limit >= data.total} onClick={() => setPage((p) => p + 1)}
            className="font-mono text-xs text-crema/30 hover:text-crema disabled:opacity-20 transition-colors px-2">
            Siguiente →
          </button>
        </div>
      </div>

      {/* Context menu */}
      {ctx && (
        <ContextMenuPortal
          x={ctx.x} y={ctx.y}
          onClose={() => setCtx(null)}
          items={[
            {
              label:   "Eliminar registro",
              icon:    <Trash2 size={11} />,
              danger:  true,
              onClick: () => deleteBackup(ctx.id),
            },
          ]}
        />
      )}
    </div>
  );
}

function DeliveryStatus({ status, phase, error, onRetry }: { status?: string; phase?: string | null; error?: string | null; onRetry?: () => void }) {
  if (status === "delivered") return <span className="text-xs text-green-400/80">Entregado</span>;
  if (status === "failed") return <button type="button" title={error ?? "Reintentar entrega"} onClick={(event) => { event.stopPropagation(); onRetry?.(); }} className="truncate text-left text-xs text-amber-400 underline decoration-amber-400/30 underline-offset-2">Reintentar</button>;
  if (status === "processing") return <span className="text-xs text-arcilla">{phase === "transferring" ? "Enviando…" : "Comprimiendo…"}</span>;
  return <span className="text-xs text-crema/30">Pendiente</span>;
}
