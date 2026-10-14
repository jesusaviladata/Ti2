"use client";

import { AgentsAdmin } from "@/components/agents/agents-admin";
import { AgentTable } from "@/components/agents/agent-table";
import { useAgents } from "@/hooks/useAgents";
import { useAuthStore } from "@/store/auth.store";

export default function ServersPage() {
  const user = useAuthStore((state) => state.user);
  return <div className="space-y-6">
    <div><p className="de-eyebrow">Infraestructura</p><h1 className="de-page-title">Servidores</h1><p className="mt-2 text-sm text-muted">Estado de conexión y configuración de tus agentes.</p></div>
    {user?.role === "admin" ? <AgentsAdmin /> : <ReadOnlyServers />}
  </div>;
}

function ReadOnlyServers() {
  const query = useAgents();
  return <AgentTable agents={query.data?.items ?? []} loading={query.isLoading} error={query.isError} />;
}
