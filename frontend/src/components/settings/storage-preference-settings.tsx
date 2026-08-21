"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, HardDrive, Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import {
  useAgentStorage,
  useClearAgentStoragePreference,
  useUpdateAgentStoragePreference,
} from "@/hooks/useAgentStorage";
import { cn, formatBytes } from "@/lib/utils";
import type { AgentVolumeState } from "@/types/agent-storage";


const AUTOMATIC = "automatic";

function optionKey(item: AgentVolumeState) {
  return `${item.agentId}::${item.volumeKey}`;
}

function capacity(item: AgentVolumeState) {
  if (item.freeBytes == null || item.totalBytes == null) return "Capacidad no disponible";
  return `${formatBytes(item.freeBytes)} libres de ${formatBytes(item.totalBytes)}`;
}

export function StoragePreferenceSettings() {
  const inventory = useAgentStorage();
  const updatePreference = useUpdateAgentStoragePreference();
  const clearPreference = useClearAgentStoragePreference();
  const [selection, setSelection] = useState(AUTOMATIC);
  const [saved, setSaved] = useState(false);

  const configuredKey = inventory.data?.preference.mode === "configured"
    ? `${inventory.data.preference.agentId}::${inventory.data.preference.volumeKey}`
    : AUTOMATIC;

  useEffect(() => {
    setSelection(configuredKey);
  }, [configuredKey]);

  const groups = useMemo(() => {
    const result = new Map<string, AgentVolumeState[]>();
    for (const item of inventory.data?.items ?? []) {
      const values = result.get(item.agentName) ?? [];
      values.push(item);
      result.set(item.agentName, values);
    }
    return [...result.entries()];
  }, [inventory.data?.items]);

  const saving = updatePreference.isPending || clearPreference.isPending;

  async function save() {
    setSaved(false);
    try {
      if (selection === AUTOMATIC) {
        await clearPreference.mutateAsync();
      } else {
        const separator = selection.indexOf("::");
        await updatePreference.mutateAsync({
          agentId: selection.slice(0, separator),
          volumeKey: selection.slice(separator + 2),
        });
      }
      setSaved(true);
    } catch {
      // React Query expone el error en pantalla; evitamos una promesa rechazada sin manejar.
    }
  }

  if (inventory.isLoading) {
    return <div className="h-48 animate-pulse rounded-[1rem] border border-musgo/20 bg-musgo/[0.05]" />;
  }

  if (inventory.isError) {
    return (
      <div className="flex items-center justify-between rounded-[1rem] border border-red-500/20 bg-red-500/[0.04] p-5">
        <div className="flex items-center gap-3 text-sm text-red-300/80">
          <TriangleAlert size={16} /> No se pudo consultar el almacenamiento de los agentes.
        </div>
        <button type="button" onClick={() => inventory.refetch()} className="text-crema/40 hover:text-crema" aria-label="Reintentar">
          <RefreshCw size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div>
        <h2 className="text-base font-medium text-crema/80">Unidad visible en el encabezado</h2>
        <p className="mt-1 text-xs leading-relaxed text-crema/35">
          Esta selección se comparte para todos los usuarios. Las demás unidades seguirán disponibles en el detalle.
        </p>
      </div>

      {inventory.data?.preference.mode === "configured" && !inventory.data.preference.available ? (
        <div className="flex items-start gap-2 rounded-[0.75rem] border border-amber-400/25 bg-amber-400/[0.05] px-3 py-2.5 text-xs text-amber-200/70">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          La unidad configurada no está reportando. Mientras tanto se muestra automáticamente la unidad con mayor riesgo.
        </div>
      ) : null}

      <div className="overflow-hidden rounded-[1rem] border border-musgo/25 bg-musgo/[0.04]">
        <button
          type="button"
          onClick={() => { setSelection(AUTOMATIC); setSaved(false); }}
          className="flex w-full items-center gap-3 border-b border-musgo/15 px-4 py-3 text-left transition-colors hover:bg-musgo/[0.08]"
        >
          <span className={cn("grid h-4 w-4 shrink-0 place-items-center rounded-full border", selection === AUTOMATIC ? "border-arcilla bg-arcilla text-carbon" : "border-musgo/50")}>{selection === AUTOMATIC ? <Check size={10} /> : null}</span>
          <div>
            <p className="text-sm text-crema/75">Automático</p>
            <p className="font-mono text-[10px] text-crema/30">Mostrar la unidad con mayor riesgo</p>
          </div>
        </button>

        <div className="max-h-[26rem] overflow-y-auto">
          {groups.map(([agentName, items]) => (
            <div key={agentName} className="border-b border-musgo/15 last:border-0">
              <p className="bg-musgo/[0.04] px-4 py-2 font-mono text-[9px] uppercase tracking-[0.14em] text-crema/25">{agentName}</p>
              {items.map((item) => {
                const key = optionKey(item);
                const selected = selection === key;
                return (
                  <button
                    type="button"
                    key={key}
                    onClick={() => { setSelection(key); setSaved(false); }}
                    className="flex w-full items-center gap-3 border-t border-musgo/10 px-4 py-3 text-left transition-colors hover:bg-musgo/[0.08]"
                  >
                    <span className={cn("grid h-4 w-4 shrink-0 place-items-center rounded-full border", selected ? "border-arcilla bg-arcilla text-carbon" : "border-musgo/50")}>{selected ? <Check size={10} /> : null}</span>
                    <HardDrive size={15} className="shrink-0 text-crema/35" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-crema/70">{item.label ? `${item.label} (${item.volumeKey})` : item.volumeKey}</span>
                      <span className="block truncate font-mono text-[10px] text-crema/30">{capacity(item)}</span>
                    </span>
                    <span className="hidden font-mono text-[9px] uppercase tracking-wider text-crema/20 sm:block">{item.roles.join(" · ") || "sin rol"}</span>
                  </button>
                );
              })}
            </div>
          ))}
          {groups.length === 0 ? <p className="px-4 py-8 text-center text-xs text-crema/30">Ningún agente ha reportado unidades todavía.</p> : null}
        </div>
      </div>

      {(updatePreference.isError || clearPreference.isError) ? <p className="text-xs text-red-400">No se pudo guardar la unidad seleccionada.</p> : null}
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-green-400/75">{saved ? "Selección guardada" : ""}</span>
        <button
          type="button"
          onClick={save}
          disabled={saving || selection === configuredKey || (selection !== AUTOMATIC && groups.length === 0)}
          className="flex h-9 items-center gap-2 rounded-[0.625rem] bg-arcilla px-4 text-xs font-medium text-carbon transition-opacity disabled:opacity-35"
        >
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
          Guardar selección
        </button>
      </div>
    </div>
  );
}
