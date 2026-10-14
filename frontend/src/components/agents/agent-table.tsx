"use client";

import { useState } from "react";
import { Search, Server, Settings2, Network, ArrowRightLeft } from "lucide-react";
import type { AgentRecord } from "@/types/agent";

export function agentState(agent: AgentRecord) {
  if (agent.revokedAt || agent.status === "revoked" || agent.healthStatus === "revoked") return { label: "Revocado", tone: "bg-danger/10 text-danger", incident: true };
  if (!agent.online || agent.healthStatus === "offline") return { label: "Sin conexión", tone: "bg-danger/10 text-danger", incident: true };
  if (agent.healthStatus === "degraded") return { label: "Requiere atención", tone: "bg-warning/10 text-warning", incident: true };
  if (agent.healthStatus === "busy") return { label: "En ejecución", tone: "bg-arcilla/10 text-arcilla", incident: false };
  return { label: "Conectado", tone: "bg-success/10 text-success", incident: false };
}

type Filter = "all" | "incident" | "busy";

export function AgentTable({ agents, loading, error, onConnections, onEdit, onReplace }: {
  agents: AgentRecord[];
  loading?: boolean;
  error?: boolean;
  onConnections?: (agent: AgentRecord) => void;
  onEdit?: (agent: AgentRecord) => void;
  onReplace?: (agent: AgentRecord) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const visible = agents.filter((agent) => {
    const matches = `${agent.hostname} ${agent.configuration?.name ?? ""}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
    return matches && (filter === "all" || (filter === "incident" ? agentState(agent).incident : agent.healthStatus === "busy" && !agentState(agent).incident));
  });
  const actions = Boolean(onConnections || onEdit || onReplace);

  return <section className="de-panel overflow-hidden" aria-label="Servidores vinculados">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-musgo/15 p-4">
      <div className="flex flex-wrap gap-2" aria-label="Filtrar servidores">
        {([["all", "Todos"], ["incident", "Con incidencias"], ["busy", "En ejecución"]] as const).map(([value, label]) => <button key={value} type="button" className="de-filter" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}
      </div>
      <label className="relative flex min-w-0 items-center gap-2 text-subtle">
        <Search size={15} className="absolute left-3" />
        <input aria-label="Buscar servidor" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar servidor…" className="h-9 w-full rounded-lg border border-musgo/25 bg-inset/50 pl-9 pr-3 text-sm text-crema sm:w-56" />
      </label>
    </div>
    {loading ? <p className="de-empty" role="status">Consultando servidores…</p> : error ? <p className="de-empty text-danger" role="alert">No se pudieron consultar los servidores. Vuelve a intentarlo.</p> : !agents.length ? <div className="de-empty"><Server size={24} className="text-subtle" /><p className="font-medium text-crema">Aún no hay servidores vinculados</p><p>Vincula el primer agente para consultar su estado aquí.</p></div> : <>
      <div className="overflow-x-auto">
        <table className="de-table">
          <thead><tr><th>Servidor</th><th>Estado</th><th>Agente</th><th>Último contacto</th>{actions ? <th className="text-right">Administrar</th> : null}</tr></thead>
          <tbody>{visible.map((agent) => { const state = agentState(agent); return <tr key={agent.id}>
            <td><p className="whitespace-nowrap font-medium">{agent.configuration?.name ?? agent.hostname}</p><p className="mt-1 text-xs text-subtle">{agent.hostname}</p></td>
            <td><span className={`de-badge whitespace-nowrap ${state.tone}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{state.label}</span></td>
            <td className="whitespace-nowrap tabular-nums text-muted">v{agent.agentVersion}</td>
            <td className="whitespace-nowrap text-xs text-muted">{agent.lastHeartbeatAt || agent.lastSeenAt ? new Date(agent.lastHeartbeatAt ?? agent.lastSeenAt!).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" }) : "Sin contacto"}</td>
            {actions ? <td><div className="flex justify-end gap-2">
              {onConnections ? <button type="button" className="de-filter flex items-center gap-1.5" onClick={() => onConnections(agent)} aria-label={`Conexiones de ${agent.hostname}`}><Network size={14} />Conexiones</button> : null}
              {onEdit ? <button type="button" disabled={!agent.online} title={!agent.online ? "Conecta el agente para configurar la raíz" : undefined} className="de-filter flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-40" onClick={() => onEdit(agent)} aria-label={`Configurar ${agent.hostname}`}><Settings2 size={14} />Configurar</button> : null}
              {onReplace ? <button type="button" disabled={agent.status === "revoked" || agent.status === "replacement_pending"} className="de-filter flex items-center gap-1.5 disabled:opacity-40" onClick={() => onReplace(agent)} aria-label={`Reemplazar ${agent.hostname}`}><ArrowRightLeft size={14} />Reemplazar</button> : null}
            </div></td> : null}
          </tr>; })}</tbody>
        </table>
      </div>
      {!visible.length ? <p className="de-empty">Ningún servidor coincide con los filtros.</p> : null}
      <p className="border-t border-musgo/15 px-5 py-3 text-xs text-subtle" role="status">{visible.length} de {agents.length} servidores</p>
    </>}
  </section>;
}
