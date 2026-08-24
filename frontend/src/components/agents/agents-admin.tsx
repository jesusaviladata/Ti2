"use client";

import { useState } from "react";
import { ArrowRightLeft, Copy, Link2, Network, ServerCog, Settings2, WifiOff } from "lucide-react";
import { useAgents, usePairingCode } from "@/hooks/useAgents";
import { AgentRootWizard } from "@/components/agents/agent-root-wizard";
import type { AgentRecord } from "@/types/agent";
import { ManagedProfilesPanel } from "@/components/agents/managed-profiles-panel";
import { AgentReplacementDialog } from "@/components/agents/agent-replacement-dialog";

export function AgentsAdmin() {
  const agentsQuery = useAgents();
  const pairing = usePairingCode();
  const [editing, setEditing] = useState<AgentRecord | null>(null);
  const [connections, setConnections] = useState<AgentRecord | null>(null);
  const [replacing, setReplacing] = useState<AgentRecord | null>(null);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm leading-relaxed text-crema/45">Los agentes ejecutan backups y limpieza localmente. Las credenciales y rutas sensibles nunca pasan por el navegador.</p>
        <button type="button" onClick={() => pairing.mutate()} className="flex h-9 items-center gap-2 rounded-[0.625rem] border border-arcilla/35 bg-arcilla/10 px-4 text-xs text-arcilla hover:bg-arcilla/15"><Link2 size={13} /> Vincular agente</button>
      </div>

      {pairing.data ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[0.875rem] border border-arcilla/25 bg-arcilla/[0.06] px-4 py-3">
          <div><p className="text-xs text-crema/45">Código de vinculación</p><p className="mt-1 font-mono text-sm tracking-wider text-crema">{pairing.data.code}</p></div>
          <button type="button" onClick={() => navigator.clipboard.writeText(pairing.data!.code)} className="flex items-center gap-2 text-xs text-arcilla"><Copy size={13} /> Copiar</button>
        </div>
      ) : null}

      <div className="overflow-hidden rounded-[1rem] border border-musgo/20 bg-musgo/[0.05]">
        {!agentsQuery.data?.items.length ? (
          <div className="p-10 text-center"><WifiOff size={22} className="mx-auto mb-3 text-crema/20" /><p className="text-sm text-crema/50">No hay agentes vinculados</p><p className="mt-1 font-mono text-[10px] text-crema/25">Genera un código e instálalo en el servidor Windows.</p></div>
        ) : agentsQuery.data.items.map((agent) => (
          <div key={agent.id} className="grid gap-3 border-b border-musgo/15 p-4 last:border-b-0 md:grid-cols-[1fr_auto] md:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2"><ServerCog size={14} className="text-arcilla/70" /><span className="text-sm font-medium text-crema/80">{agent.configuration?.name ?? agent.hostname}</span><span className={agent.online ? "font-mono text-[10px] text-green-400" : "font-mono text-[10px] text-red-400"}>● {agent.online ? "Conectado" : "Desconectado"}</span></div>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] text-crema/35"><span>{agent.hostname} · v{agent.agentVersion}</span><span>{agent.configuration?.root ?? "Raíz pendiente"}</span><span>{agent.metadata.sqlInstances?.length ?? 0} perfiles SQL</span><span>Último contacto: {agent.lastSeenAt ? new Date(agent.lastSeenAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" }) : "nunca"}</span></div>
            </div>
            <div className="flex flex-wrap gap-2"><button type="button" onClick={() => setConnections(agent)} className="flex h-8 items-center justify-center gap-2 rounded-[0.5rem] border border-musgo/25 px-3 text-xs text-crema/55 hover:border-arcilla/30 hover:text-crema"><Network size={12} /> Conexiones</button><button type="button" onClick={() => setReplacing(agent)} disabled={agent.status === "revoked" || agent.status === "replacement_pending"} className="flex h-8 items-center justify-center gap-2 rounded-[0.5rem] border border-musgo/25 px-3 text-xs text-crema/55 hover:border-arcilla/30 hover:text-crema disabled:opacity-30"><ArrowRightLeft size={12} /> Reemplazar</button><button type="button" disabled={!agent.online} title={agent.online ? undefined : "Conecte el agente para configurar la raíz"} onClick={() => setEditing(agent)} className="flex h-8 items-center justify-center gap-2 rounded-[0.5rem] border border-musgo/25 px-3 text-xs text-crema/55 hover:border-arcilla/30 hover:text-crema disabled:cursor-not-allowed disabled:opacity-30"><Settings2 size={12} /> {agent.configuration ? "Editar raíz" : "Configurar raíz"}</button></div>
          </div>
        ))}
      </div>
      {connections ? <ManagedProfilesPanel agent={connections} onClose={() => setConnections(null)} /> : null}
      {editing ? <AgentRootWizard agent={editing} onClose={() => setEditing(null)} /> : null}
      {replacing ? <AgentReplacementDialog agent={replacing} onClose={() => setReplacing(null)} /> : null}
    </div>
  );
}
