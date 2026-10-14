"use client";

import { useState } from "react";
import { Copy, Link2 } from "lucide-react";
import { useAgents, usePairingCode } from "@/hooks/useAgents";
import { AgentTable } from "@/components/agents/agent-table";
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
        <p className="max-w-2xl text-sm leading-relaxed text-muted">Vincula y administra los agentes que protegen tus servidores.</p>
        <button type="button" disabled={pairing.isPending} onClick={() => pairing.mutate()} className="flex h-9 items-center gap-2 rounded-[0.625rem] border border-arcilla/35 bg-arcilla/10 px-4 text-xs text-arcilla hover:bg-arcilla/15"><Link2 size={13} /> Vincular agente</button>
      </div>

      {pairing.isError ? <p role="alert" className="text-sm text-danger">No se pudo generar el código. Inténtalo nuevamente.</p> : null}
      {pairing.data ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[0.875rem] border border-arcilla/25 bg-arcilla/[0.06] px-4 py-3">
          <div><p className="text-xs text-muted">Código de vinculación</p><p className="mt-1 font-sans text-sm tracking-wider text-crema">{pairing.data.code}</p></div>
          <button type="button" onClick={() => navigator.clipboard.writeText(pairing.data!.code)} className="flex items-center gap-2 text-xs text-arcilla"><Copy size={13} /> Copiar</button>
        </div>
      ) : null}

      <AgentTable agents={agentsQuery.data?.items ?? []} loading={agentsQuery.isLoading} error={agentsQuery.isError} onConnections={setConnections} onEdit={setEditing} onReplace={setReplacing} />
      {connections ? <ManagedProfilesPanel agent={connections} onClose={() => setConnections(null)} /> : null}
      {editing ? <AgentRootWizard agent={editing} onClose={() => setEditing(null)} /> : null}
      {replacing ? <AgentReplacementDialog agent={replacing} onClose={() => setReplacing(null)} /> : null}
    </div>
  );
}
