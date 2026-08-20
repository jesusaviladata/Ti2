"use client";

import { useState } from "react";
import { ChevronDown, Database, HardDrive, RefreshCw, TriangleAlert } from "lucide-react";
import { useAgentStorage } from "@/hooks/useAgentStorage";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { AgentVolumeState } from "@/types/agent-storage";


const stateStyles = {
  healthy: { bar: "bg-emerald-500", text: "text-emerald-300", border: "border-emerald-500/20" },
  warning: { bar: "bg-amber-400", text: "text-amber-300", border: "border-amber-400/25" },
  critical: { bar: "bg-red-500", text: "text-red-300", border: "border-red-500/30" },
  unknown: { bar: "bg-crema/20", text: "text-crema/35", border: "border-musgo/25" },
} as const;

function volumeName(item: AgentVolumeState) {
  return item.label ? `${item.label} (${item.volumeKey})` : item.volumeKey;
}

function capacityText(item: AgentVolumeState) {
  if (item.freeBytes == null || item.totalBytes == null) return "Capacidad no disponible";
  return `${formatBytes(item.freeBytes)} disponibles de ${formatBytes(item.totalBytes)}`;
}

function ageText(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  return `hace ${Math.floor(seconds / 3600)} h`;
}

function VolumeMeter({ item, compact = false }: { item: AgentVolumeState; compact?: boolean }) {
  const styles = stateStyles[item.state];
  const used = item.freePercent == null ? 0 : Math.max(0, Math.min(100, 100 - item.freePercent));
  return (
    <div className={cn("min-w-0", compact ? "grid grid-cols-[minmax(140px,0.7fr)_minmax(220px,1fr)_auto] items-center gap-4" : "flex items-center gap-4")}>
      <div className="flex min-w-0 items-center gap-2.5">
        <HardDrive size={18} className={cn("shrink-0", styles.text)} />
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-crema/80">{volumeName(item)}</p>
          <p className="truncate text-[10px] text-crema/30">{item.agentName} · {ageText(item.observedAt)}</p>
        </div>
      </div>
      <div className="min-w-0">
        <div
          role="progressbar"
          aria-label={`Espacio utilizado en ${volumeName(item)}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={item.freePercent == null ? undefined : Math.round(used)}
          aria-valuetext={capacityText(item)}
          className="h-2 overflow-hidden rounded-sm border border-musgo/30 bg-carbon/70"
        >
          <div className={cn("h-full transition-[width] duration-500", styles.bar)} style={{ width: `${used}%` }} />
        </div>
        <p className={cn("mt-1 text-[10px] tabular-nums", styles.text)}>{capacityText(item)}</p>
      </div>
      {compact ? <span className="hidden text-[10px] uppercase tracking-wider text-crema/25 xl:block">{item.roles.join(" · ")}</span> : null}
    </div>
  );
}

export function StorageHealthBar() {
  const { data, isLoading, isError, refetch, isFetching } = useAgentStorage();
  const [expanded, setExpanded] = useState(false);
  const summary = data?.summary;

  if (isLoading) {
    return <div className="h-14 shrink-0 animate-pulse border-b border-musgo/15 bg-musgo/[0.06]" aria-label="Cargando capacidad de almacenamiento" />;
  }

  if (isError || !summary) {
    return (
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-musgo/15 bg-musgo/[0.04] px-6">
        <div className="flex items-center gap-2 text-xs text-crema/30">
          <Database size={14} /> {isError ? "No se pudo consultar el espacio de los agentes" : "Sin telemetría de almacenamiento"}
        </div>
        <button type="button" onClick={() => refetch()} className="text-crema/30 hover:text-crema" aria-label="Actualizar almacenamiento"><RefreshCw size={13} className={isFetching ? "animate-spin" : ""} /></button>
      </div>
    );
  }

  const styles = stateStyles[summary.state];
  return (
    <section className={cn("relative z-20 shrink-0 border-b bg-carbon/95", styles.border)} aria-label="Estado de almacenamiento de agentes">
      <div className="grid min-h-14 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-6 py-2">
        <VolumeMeter item={summary} compact />
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="flex h-8 items-center gap-1.5 rounded-[0.5rem] border border-musgo/25 px-2.5 text-[10px] text-crema/40 hover:border-musgo/45 hover:text-crema/70"
          aria-expanded={expanded}
        >
          {summary.state === "critical" ? <TriangleAlert size={12} className="text-red-400" /> : null}
          {data.total > 1 ? `${data.total} unidades` : "Detalle"}
          <ChevronDown size={12} className={cn("transition-transform", expanded && "rotate-180")} />
        </button>
      </div>
      {expanded ? (
        <div className="absolute left-0 right-0 top-full border-b border-musgo/25 bg-carbon px-6 py-3 shadow-2xl">
          <div className="grid gap-3 lg:grid-cols-2">
            {data.items.map((item) => <VolumeMeter key={`${item.agentId}:${item.volumeKey}`} item={item} />)}
          </div>
        </div>
      ) : null}
    </section>
  );
}
