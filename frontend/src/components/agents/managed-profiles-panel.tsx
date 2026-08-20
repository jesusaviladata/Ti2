"use client";

import { useState } from "react";
import { Database, Loader2, Network, Pencil, Plus, Trash2, X } from "lucide-react";
import { useDeleteManagedProfile, useManagedAgentProfiles, useTestManagedProfile } from "@/hooks/useAgentProfilesAdmin";
import { AgentConnectionWizard } from "@/components/agents/agent-connection-wizard";
import type { AgentRecord } from "@/types/agent";


const statusLabel = { pending: "Pendiente", applied: "Aplicado", error: "Error" } as const;

export function ManagedProfilesPanel({ agent, onClose }: { agent: AgentRecord; onClose: () => void }) {
  const profiles = useManagedAgentProfiles(agent.id);
  const remove = useDeleteManagedProfile(agent.id);
  const test = useTestManagedProfile(agent.id);
  const [wizard, setWizard] = useState(false);
  return (
    <div className="rounded-[1rem] border border-arcilla/20 bg-musgo/[0.05] p-5">
      <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium text-crema/75">Conexiones de {agent.hostname}</p><p className="mt-1 text-xs text-crema/35">Edite SQL Server y destinos desde aquí; los secretos sólo se abren en este agente.</p></div><button type="button" onClick={onClose} className="text-crema/30"><X size={15} /></button></div>
      <div className="mt-4 space-y-2">{profiles.isLoading ? <p className="text-xs text-crema/30">Cargando…</p> : null}{profiles.data?.items.map((item) => <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-[0.75rem] border border-musgo/20 px-4 py-3"><span className="grid h-8 w-8 place-items-center rounded-[0.5rem] bg-musgo/20">{item.profileType === "sql" ? <Database size={14} className="text-arcilla" /> : <Network size={14} className="text-arcilla" />}</span><div className="min-w-0 flex-1"><p className="truncate text-sm text-crema/70">{item.label}</p><p className="mt-0.5 text-[10px] text-crema/30">{item.profileType === "sql" ? String(item.publicConfig.server ?? "SQL") : `${String(item.publicConfig.type ?? "").toUpperCase()} · ${String(item.publicConfig.path ?? "")}`}</p></div><span className={item.syncStatus === "applied" ? "text-[10px] text-green-400" : item.syncStatus === "error" ? "text-[10px] text-red-400" : "text-[10px] text-amber-400"}>{statusLabel[item.syncStatus]}</span><button type="button" onClick={() => test.mutate(item.id)} className="rounded-[0.5rem] border border-musgo/25 px-2.5 py-1.5 text-[10px] text-crema/45">{test.isPending ? <Loader2 size={11} className="animate-spin" /> : "Probar"}</button><button type="button" onClick={() => { if (window.confirm(`¿Eliminar ${item.label}?`)) remove.mutate(item.id); }} className="text-red-400/60"><Trash2 size={13} /></button></div>)}{!profiles.isLoading && !profiles.data?.items.length ? <p className="rounded-[0.75rem] border border-dashed border-musgo/25 p-5 text-center text-xs text-crema/30">No hay perfiles administrados todavía.</p> : null}</div>
      <button type="button" onClick={() => setWizard(true)} className="mt-4 flex h-9 items-center gap-2 rounded-[0.5rem] border border-arcilla/30 bg-arcilla/10 px-4 text-xs text-arcilla"><Plus size={13} /> Asistente de conexión</button>
      {wizard ? <AgentConnectionWizard agent={agent} onClose={() => setWizard(false)} /> : null}
    </div>
  );
}
