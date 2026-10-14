"use client";

import { ClipboardList, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { useCleanupHistory } from "@/hooks/useCleanup";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { CleanupStatus } from "@/types/cleanup";

const STATUS_CONFIG: Record<CleanupStatus, { label: string; icon: React.ElementType; classes: string; dot: string }> = {
  completed: { label: "Completado", icon: CheckCircle2,   classes: "bg-success/10 text-success border-green-800/30",  dot: "bg-green-400" },
  partial:   { label: "Parcial",    icon: AlertTriangle,  classes: "bg-yellow-900/15 text-yellow-400 border-yellow-800/25", dot: "bg-yellow-400" },
  failed:    { label: "Fallido",    icon: XCircle,        classes: "bg-danger/10 text-danger border-red-800/30",         dot: "bg-red-400" },
};

export function CleanupHistory() {
  const { data } = useCleanupHistory();
  const entries = data?.items ?? [];

  if (!entries.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-[0.75rem] bg-surface flex items-center justify-center mb-3">
          <ClipboardList size={20} className="text-subtle" />
        </div>
        <p className="font-sans text-sm text-muted">Sin historial</p>
        <p className="font-sans text-xs text-subtle mt-1">
          Las limpiezas ejecutadas quedarán registradas aquí
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Table header */}
      <div className="grid grid-cols-[110px_80px_90px_80px_100px] gap-3 px-4 py-2 text-xs font-sans text-subtle uppercase tracking-wider border-b border-musgo/15">
        <span>Fecha</span>
        <span>Archivos</span>
        <span>Liberado</span>
        <span>Errores</span>
        <span>Estado</span>
      </div>

      <div className="divide-y divide-musgo/10">
        {entries.map((entry) => {
          const cfg = STATUS_CONFIG[entry.status];
          return (
            <div
              key={entry.id}
              className="grid grid-cols-[110px_80px_90px_80px_100px] gap-3 px-4 py-3.5 items-center hover:bg-musgo/5 transition-colors"
            >
              <span className="font-sans text-xs text-muted">
                {new Date(entry.executedAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}
              </span>
              <span className="font-sans text-xs text-crema">{entry.filesDeleted}</span>
              <span className="font-sans text-xs text-arcilla/70">{formatBytes(entry.bytesFreed)}</span>
              <span className={cn("font-sans text-xs", entry.errors > 0 ? "text-danger" : "text-subtle")}>
                {entry.errors || "—"}
              </span>
              <span className={cn(
                "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-sans border w-fit",
                cfg.classes
              )}>
                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />
                {cfg.label}
              </span>
            </div>
          );
        })}
      </div>

      <div className="px-4 py-3 border-t border-musgo/15">
        <span className="font-sans text-xs text-subtle">
          {data?.total} operacion{data?.total !== 1 ? "es" : ""} en total
        </span>
      </div>
    </div>
  );
}
