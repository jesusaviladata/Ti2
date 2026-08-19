"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Database, Power, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useAgentBackupPlans,
  useAgentDatabases,
  useBackupAgents,
  useCreateAgentBackupPlan,
  useDeleteAgentBackupPlan,
  useUpdateAgentBackupPlan,
} from "@/hooks/useBackups";

const INPUT = "w-full rounded-xl border border-musgo/25 bg-musgo/10 px-3 py-2.5 text-sm text-crema outline-none focus:border-arcilla/50";

function displayDate(value?: string | null) {
  if (!value) return "Pendiente";
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Mexico_City",
  }).format(new Date(value));
}

export function BackupAutomationList({ onNew }: { onNew: () => void }) {
  const { data, isLoading } = useAgentBackupPlans();
  const update = useUpdateAgentBackupPlan();
  const remove = useDeleteAgentBackupPlan();
  const plans = data?.items ?? [];

  return (
    <section className="rounded-[1.25rem] border border-musgo/20 bg-musgo/10 p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-arcilla">Automatización</p>
          <h2 className="mt-1 text-lg font-semibold text-crema">Full L/Mi/V · Diferencial Ma/J</h2>
          <p className="mt-1 text-xs text-crema/40">Cada agente procesa sus bases en lotes de hasta 100.</p>
        </div>
        <Button onClick={onNew} variant="outline" className="gap-2 shrink-0">
          <CalendarClock size={14} /> Programar
        </Button>
      </div>

      {isLoading && <p className="font-mono text-xs text-crema/35">Cargando planes…</p>}
      {!isLoading && plans.length === 0 && (
        <div className="rounded-xl border border-dashed border-musgo/25 px-4 py-5 text-center text-xs text-crema/35">
          Todavía no hay planes automáticos.
        </div>
      )}
      {plans.map((plan) => (
        <div key={plan.id} className="flex flex-col gap-3 rounded-xl border border-musgo/20 bg-carbon p-4 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${plan.enabled ? "bg-green-400" : "bg-crema/25"}`} />
              <p className="truncate text-sm font-medium text-crema">{plan.name}</p>
            </div>
            <p className="mt-1 font-mono text-[10px] text-crema/35">
              {plan.databaseNames.length} bases · {plan.localTime} CDMX · Próximo: {displayDate(plan.nextRunAt)}
            </p>
          </div>
          <button
            type="button"
            onClick={() => update.mutate({ planId: plan.id, payload: { enabled: !plan.enabled } })}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-musgo/25 px-3 py-2 text-xs text-crema/60 hover:text-crema"
          >
            <Power size={13} /> {plan.enabled ? "Pausar" : "Activar"}
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`¿Eliminar el plan ${plan.name}?`)) remove.mutate(plan.id);
            }}
            className="inline-flex items-center justify-center rounded-lg border border-red-500/20 p-2 text-red-400/70 hover:text-red-400"
            aria-label={`Eliminar ${plan.name}`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
    </section>
  );
}

export function BackupAutomationModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: agentsData } = useBackupAgents(open);
  const agents = agentsData?.items ?? [];
  const [agentId, setAgentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [destinationId, setDestinationId] = useState("");
  const [localTime, setLocalTime] = useState("02:00");
  const [name, setName] = useState("Respaldos automáticos");
  const selectedAgent = useMemo(() => agents.find((item) => item.id === agentId), [agents, agentId]);
  const databases = useAgentDatabases(agentId, profileId, open && !!agentId && !!profileId);
  const create = useCreateAgentBackupPlan();

  useEffect(() => {
    if (open && !agentId && agents[0]) setAgentId(agents[0].id);
  }, [open, agents, agentId]);

  useEffect(() => {
    const firstProfile = selectedAgent?.sqlInstances[0]?.id ?? "";
    if (!selectedAgent?.sqlInstances.some((item) => item.id === profileId)) setProfileId(firstProfile);
    const firstDestination = selectedAgent?.backupDestinations[0]?.id ?? "";
    if (!selectedAgent?.backupDestinations.some((item) => item.id === destinationId)) setDestinationId(firstDestination);
  }, [selectedAgent, profileId, destinationId]);

  useEffect(() => {
    if (selectedAgent && profileId) {
      const label = selectedAgent.sqlInstances.find((item) => item.id === profileId)?.label ?? profileId;
      setName(`Automático - ${selectedAgent.hostname} - ${label}`);
    }
  }, [selectedAgent, profileId]);

  if (!open) return null;
  const databaseNames = databases.data?.databases ?? [];
  const error = (create.error as any)?.response?.data?.error?.message ?? (create.error ? "No se pudo guardar el plan" : "");

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-[1.5rem] border border-musgo/40 bg-carbon shadow-2xl shadow-black/60">
        <div className="flex items-start justify-between border-b border-musgo/20 px-6 py-5">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-arcilla">Programación automática</p>
            <h2 className="mt-1 text-2xl font-semibold text-crema">Full y diferenciales</h2>
          </div>
          <button onClick={onClose} className="p-2 text-crema/40 hover:text-crema" aria-label="Cerrar"><X size={18} /></button>
        </div>

        <div className="space-y-5 p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-xs text-crema/45">
              Servidor / agente
              <select className={INPUT} value={agentId} onChange={(event) => setAgentId(event.target.value)}>
                {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.hostname} — {agent.status}</option>)}
              </select>
            </label>
            <label className="space-y-2 text-xs text-crema/45">
              Instancia SQL
              <select className={INPUT} value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                {selectedAgent?.sqlInstances.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}
              </select>
            </label>
            <label className="space-y-2 text-xs text-crema/45">
              Destino
              <select className={INPUT} value={destinationId} onChange={(event) => setDestinationId(event.target.value)}>
                <option value="">Solo ZIP local</option>
                {selectedAgent?.backupDestinations.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}
              </select>
            </label>
            <label className="space-y-2 text-xs text-crema/45">
              Hora de inicio (Ciudad de México)
              <input className={INPUT} type="time" value={localTime} onChange={(event) => setLocalTime(event.target.value)} />
            </label>
          </div>

          <label className="block space-y-2 text-xs text-crema/45">
            Nombre del plan
            <input className={INPUT} value={name} onChange={(event) => setName(event.target.value)} maxLength={255} />
          </label>

          <div className="rounded-xl border border-musgo/20 bg-musgo/10 p-4">
            <div className="flex items-center gap-2 text-sm text-crema"><Database size={15} className="text-arcilla" /> Bases incluidas</div>
            {databases.isLoading && <p className="mt-2 font-mono text-xs text-crema/35">Consultando al agente…</p>}
            {databases.data && (
              <p className="mt-2 font-mono text-xs text-crema/45">
                {databaseNames.length} bases encontradas. Se guardarán en lotes automáticos de máximo 100.
              </p>
            )}
            {databases.data?.error && <p className="mt-2 text-xs text-red-400">{databases.data.error}</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-arcilla/25 bg-arcilla/5 p-4">
              <p className="text-sm font-medium text-crema">Backup completo</p>
              <p className="mt-1 font-mono text-xs text-crema/45">Lunes · Miércoles · Viernes</p>
            </div>
            <div className="rounded-xl border border-blue-400/20 bg-blue-400/5 p-4">
              <p className="text-sm font-medium text-crema">Backup diferencial</p>
              <p className="mt-1 font-mono text-xs text-crema/45">Martes · Jueves</p>
            </div>
          </div>
          <p className="font-mono text-[10px] leading-relaxed text-crema/35">
            La primera ejecución será Full para establecer una base válida, aunque corresponda a martes o jueves.
          </p>

          {error && <p className="rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2 text-xs text-red-400">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 border-t border-musgo/20 px-6 py-4">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            disabled={!agentId || !profileId || !name.trim() || databaseNames.length === 0 || create.isPending}
            onClick={() => create.mutate({
              name: name.trim(),
              agentId,
              sqlProfileId: profileId,
              destinationProfileId: destinationId || undefined,
              databaseNames,
              localTime,
              timezone: "America/Mexico_City",
              enabled: true,
            }, { onSuccess: onClose })}
          >
            {create.isPending ? "Guardando…" : `Programar ${databaseNames.length} bases`}
          </Button>
        </div>
      </div>
    </div>
  );
}
