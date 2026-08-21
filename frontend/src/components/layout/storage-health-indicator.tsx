"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, HardDrive, RefreshCw, TriangleAlert } from "lucide-react";
import { useAgentStorage } from "@/hooks/useAgentStorage";
import { cn, formatBytes } from "@/lib/utils";
import type { AgentVolumeState } from "@/types/agent-storage";


const stateStyles = {
  healthy: {
    bar: "bg-emerald-500",
    text: "text-emerald-300",
    border: "border-emerald-500/20",
    surface: "bg-emerald-500/[0.04]",
    label: "Saludable",
  },
  warning: {
    bar: "bg-amber-400",
    text: "text-amber-300",
    border: "border-amber-400/25",
    surface: "bg-amber-400/[0.05]",
    label: "Poco espacio",
  },
  critical: {
    bar: "bg-red-500",
    text: "text-red-300",
    border: "border-red-500/30",
    surface: "bg-red-500/[0.05]",
    label: "Espacio crítico",
  },
  unknown: {
    bar: "bg-crema/20",
    text: "text-crema/35",
    border: "border-musgo/25",
    surface: "bg-musgo/[0.05]",
    label: "Sin lectura",
  },
} as const;

function volumeName(item: AgentVolumeState) {
  return item.label ? `${item.label} (${item.volumeKey})` : item.volumeKey;
}

function capacityText(item: AgentVolumeState) {
  if (item.freeBytes == null || item.totalBytes == null) return "Capacidad no disponible";
  return `${formatBytes(item.freeBytes)} disponibles de ${formatBytes(item.totalBytes)}`;
}

function compactCapacityText(item: AgentVolumeState) {
  if (item.freeBytes == null) return "Sin datos";
  return `${formatBytes(item.freeBytes)} libres`;
}

function ageText(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  return `hace ${Math.floor(seconds / 3600)} h`;
}

function CompactVolume({ item, secondary = false }: { item: AgentVolumeState; secondary?: boolean }) {
  const styles = stateStyles[item.state];
  const used = item.freePercent == null ? 0 : Math.max(0, Math.min(100, 100 - item.freePercent));

  return (
    <span
      className={cn(
        "min-w-0 flex-1 items-center gap-2 px-2.5",
        secondary ? "hidden xl:flex border-l border-musgo/20" : "flex",
      )}
    >
      <HardDrive size={14} className={cn("shrink-0", styles.text)} />
      <span className="min-w-0 flex-1 text-left">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate font-sans text-[11px] font-medium text-crema/75">
            {volumeName(item)}
          </span>
          <span className={cn("shrink-0 font-mono text-[9px] tabular-nums", styles.text)}>
            {compactCapacityText(item)}
          </span>
        </span>
        <span className="mt-1 block h-1 overflow-hidden rounded-full bg-carbon/80">
          <span
            className={cn("block h-full rounded-full transition-[width] duration-500", styles.bar)}
            style={{ width: `${used}%` }}
          />
        </span>
      </span>
    </span>
  );
}

function VolumeDetail({ item }: { item: AgentVolumeState }) {
  const styles = stateStyles[item.state];
  const used = item.freePercent == null ? 0 : Math.max(0, Math.min(100, 100 - item.freePercent));

  return (
    <div className="grid gap-3 border-b border-musgo/15 px-4 py-3 last:border-0 sm:grid-cols-[minmax(150px,0.75fr)_minmax(220px,1fr)_auto] sm:items-center">
      <div className="flex min-w-0 items-center gap-2.5">
        <HardDrive size={16} className={cn("shrink-0", styles.text)} />
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-crema/80">{volumeName(item)}</p>
          <p className="truncate font-mono text-[9px] text-crema/30">
            {item.agentName} · {ageText(item.observedAt)}
          </p>
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
          className="h-1.5 overflow-hidden rounded-full border border-musgo/25 bg-carbon/80"
        >
          <div
            className={cn("h-full rounded-full transition-[width] duration-500", styles.bar)}
            style={{ width: `${used}%` }}
          />
        </div>
        <p className={cn("mt-1 font-mono text-[9px] tabular-nums", styles.text)}>
          {capacityText(item)}
        </p>
      </div>
      <div className="flex items-center justify-between gap-3 sm:block sm:text-right">
        <p className={cn("font-mono text-[9px] uppercase tracking-wider", styles.text)}>
          {styles.label}
        </p>
        <p className="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-crema/25">
          {item.roles.length > 0 ? item.roles.join(" · ") : "Sin rol"}
        </p>
      </div>
    </div>
  );
}

export function StorageHealthIndicator() {
  const { data, isLoading, isError, refetch, isFetching } = useAgentStorage();
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const summary = data?.summary;

  useEffect(() => {
    if (!expanded) return;

    function closeOnOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setExpanded(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setExpanded(false);
    }

    document.addEventListener("mousedown", closeOnOutsideClick);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [expanded]);

  if (isLoading) {
    return (
      <div
        className="h-9 w-9 shrink-0 animate-pulse rounded-[0.75rem] border border-musgo/15 bg-musgo/[0.06] lg:h-10 lg:w-full lg:max-w-[15rem] xl:max-w-[30rem]"
        aria-label="Cargando capacidad de almacenamiento"
      />
    );
  }

  if (isError || !summary || !data) {
    return (
      <button
        type="button"
        onClick={() => refetch()}
        className="flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-[0.75rem] border border-musgo/20 text-crema/35 transition-colors hover:border-musgo/40 hover:text-crema/70 lg:w-auto lg:px-3"
        aria-label="Actualizar telemetría de almacenamiento"
      >
        <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
        <span className="hidden font-mono text-[9px] xl:inline">
          {isError ? "Espacio no disponible" : "Sin telemetría"}
        </span>
      </button>
    );
  }

  const styles = stateStyles[summary.state];
  const visibleItems = data.items.slice(0, 2);

  return (
    <div ref={containerRef} className="relative min-w-0 shrink-0 lg:w-full lg:max-w-[15rem] lg:flex-1 xl:max-w-[30rem]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-[0.75rem] border transition-colors lg:h-10 lg:w-full lg:justify-start",
          styles.border,
          styles.surface,
          "hover:border-musgo/50",
        )}
        aria-label={`Almacenamiento: ${styles.label}. ${capacityText(summary)}`}
        aria-haspopup="dialog"
        aria-expanded={expanded}
      >
        <span className="relative lg:hidden">
          <HardDrive size={15} className={styles.text} />
          <span className={cn("absolute -right-1 -top-1 h-1.5 w-1.5 rounded-full", styles.bar)} />
        </span>

        <span className="hidden min-w-0 flex-1 lg:flex">
          {visibleItems.map((item, index) => (
            <CompactVolume
              key={`${item.agentId}:${item.volumeKey}`}
              item={item}
              secondary={index === 1}
            />
          ))}
        </span>

        <span className="hidden shrink-0 items-center gap-1 border-l border-musgo/20 px-2 text-crema/30 lg:flex">
          {summary.state === "critical" ? <TriangleAlert size={11} className="text-red-400" /> : null}
          <ChevronDown size={12} className={cn("transition-transform", expanded && "rotate-180")} />
        </span>
      </button>

      {expanded ? (
        <div
          role="dialog"
          aria-label="Detalle de almacenamiento de agentes"
          className="fixed left-3 right-3 top-[4.25rem] z-[70] overflow-hidden rounded-[1rem] border border-musgo/30 bg-carbon shadow-2xl lg:absolute lg:left-0 lg:right-auto lg:top-full lg:mt-2 lg:w-[min(40rem,calc(100vw-4rem))]"
        >
          <div className="flex items-center justify-between border-b border-musgo/20 px-4 py-2.5">
            <div>
              <p className="font-sans text-xs font-medium text-crema/75">Almacenamiento de agentes</p>
              <p className="font-mono text-[9px] text-crema/30">
                {data.total} {data.total === 1 ? "unidad supervisada" : "unidades supervisadas"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => refetch()}
              className="flex h-7 w-7 items-center justify-center rounded-[0.5rem] text-crema/30 transition-colors hover:bg-musgo/15 hover:text-crema/70"
              aria-label="Actualizar almacenamiento"
            >
              <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="max-h-[min(60vh,28rem)] overflow-y-auto">
            {data.items.map((item) => (
              <VolumeDetail key={`${item.agentId}:${item.volumeKey}`} item={item} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
