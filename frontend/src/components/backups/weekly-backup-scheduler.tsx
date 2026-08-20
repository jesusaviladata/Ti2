"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Check, Loader2, Trash2, X } from "lucide-react";
import { useAgentJob, useAgentProfiles } from "@/hooks/useAgents";
import { useAgentBackupPlans, useCreateAgentBackupPlan, useDeleteAgentBackupPlan } from "@/hooks/useBackups";
import { agentsService } from "@/services/agents.service";
import type { AgentBackupPlan } from "@/types/backup";

const DAYS = ["L", "Ma", "Mi", "J", "V", "S", "D"];

export function planSummary(plan: Pick<AgentBackupPlan, "fullDays" | "differentialDays">) {
  const full = plan.fullDays.map((day) => DAYS[day]).join("/");
  const differential = plan.differentialDays.map((day) => DAYS[day]).join("/");
  return differential ? `Full ${full} · Diferencial ${differential}` : `Full ${full}`;
}

export function WeeklyBackupScheduler({ agentId }: { agentId: string | null }) {
  const plansQuery = useAgentBackupPlans();
  const remove = useDeleteAgentBackupPlan();
  const [open, setOpen] = useState(false);
  const plans = (plansQuery.data?.items ?? []).filter((plan) => plan.agentId === agentId);
  return (
    <section className="rounded-[1.25rem] border border-musgo/20 bg-musgo/[0.06] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="font-mono text-[10px] uppercase tracking-[0.18em] text-arcilla">Automatización</p><h2 className="mt-1 text-sm font-medium text-crema/75">{plans[0] ? planSummary(plans[0]) : "Plan semanal"}</h2><p className="mt-1 text-xs text-crema/30">Full obligatorio · Diferencial opcional · ejecución 02:00 CDMX</p></div>
        <button type="button" onClick={() => setOpen(true)} disabled={!agentId} className="flex h-9 items-center gap-2 rounded-full border border-arcilla/30 px-4 text-xs text-crema/70 hover:bg-arcilla/10 disabled:opacity-35"><CalendarDays size={13} /> Programar</button>
      </div>
      <div className="mt-4 overflow-hidden rounded-[0.75rem] border border-musgo/15">
        {!plans.length ? <p className="p-5 text-center text-xs text-crema/25">Todavía no hay planes automáticos para este agente.</p> : plans.map((plan) => <div key={plan.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-musgo/10 px-4 py-3 last:border-b-0"><div><p className="text-xs text-crema/65">{planSummary(plan)}</p><p className="mt-1 font-mono text-[10px] text-crema/30">{plan.databaseNames.length} base{plan.databaseNames.length === 1 ? "" : "s"} · {plan.databaseNames.slice(0, 3).join(", ")}{plan.databaseNames.length > 3 ? "…" : ""}</p></div><button type="button" title="Eliminar plan" onClick={() => remove.mutate(plan.id)} className="text-crema/25 hover:text-red-400"><Trash2 size={13} /></button></div>)}
      </div>
      {open && agentId ? <PlanModal agentId={agentId} onClose={() => setOpen(false)} /> : null}
    </section>
  );
}

function PlanModal({ agentId, onClose }: { agentId: string; onClose: () => void }) {
  const profiles = useAgentProfiles(agentId);
  const create = useCreateAgentBackupPlan();
  const [sqlProfileId, setSqlProfileId] = useState("");
  const [destinationProfileId, setDestinationProfileId] = useState("");
  const [catalogJobId, setCatalogJobId] = useState<string | null>(null);
  const catalog = useAgentJob<{ databases: string[] }>(catalogJobId);
  const [databases, setDatabases] = useState<string[]>([]);
  const [fullDays, setFullDays] = useState<number[]>([]);
  const [differentialDays, setDifferentialDays] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sqlProfileId && profiles.data?.sqlInstances[0]) setSqlProfileId(profiles.data.sqlInstances[0].id);
  }, [profiles.data, sqlProfileId]);
  useEffect(() => { setCatalogJobId(null); setDatabases([]); }, [sqlProfileId]);
  const available = catalog.data?.status === "completed" ? catalog.data.result?.databases ?? [] : [];

  function toggleDay(kind: "full" | "differential", day: number) {
    if (kind === "full") {
      setFullDays((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort());
      setDifferentialDays((current) => current.filter((item) => item !== day));
    } else {
      setDifferentialDays((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort());
      setFullDays((current) => current.filter((item) => item !== day));
    }
  }

  async function loadCatalog() {
    if (!sqlProfileId) return;
    setCatalogJobId((await agentsService.createDatabaseCatalog(agentId, sqlProfileId)).jobId);
  }

  async function save() {
    setError(null);
    try {
      await create.mutateAsync({ agentId, sqlProfileId, destinationProfileId: destinationProfileId || undefined, databaseNames: databases, fullDays, differentialDays, hourUtc: 8 });
      onClose();
    } catch (exception) {
      const value = exception as { response?: { data?: { detail?: string | { message?: string }; error?: { message?: string } } } };
      const detail = value.response?.data?.detail;
      setError(typeof detail === "string" ? detail : detail?.message ?? value.response?.data?.error?.message ?? "No fue posible guardar el plan.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <button type="button" aria-label="Cerrar" onClick={onClose} className="absolute inset-0 bg-carbon/85 backdrop-blur-sm" />
      <section className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-[1.25rem] border border-musgo/30 bg-carbon p-6">
        <div className="flex items-start justify-between"><div><p className="font-mono text-[10px] uppercase tracking-[0.18em] text-arcilla">Automatización</p><h2 className="mt-1 text-xl font-medium text-crema">Plan semanal</h2></div><button type="button" onClick={onClose} className="text-crema/30"><X size={17} /></button></div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <label className="space-y-1.5"><span className="text-[10px] uppercase tracking-wider text-crema/35">Instancia SQL</span><select value={sqlProfileId} onChange={(event) => setSqlProfileId(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-xs text-crema/65"><option value="">Seleccionar</option>{profiles.data?.sqlInstances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label className="space-y-1.5"><span className="text-[10px] uppercase tracking-wider text-crema/35">Entrega</span><select value={destinationProfileId} onChange={(event) => setDestinationProfileId(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-xs text-crema/65"><option value="">Sólo local</option>{profiles.data?.backupDestinations.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        </div>
        <div className="mt-5 overflow-x-auto rounded-[0.875rem] border border-musgo/20 p-4">
          <div className="grid min-w-[520px] grid-cols-[120px_repeat(7,1fr)] gap-2 text-center"><span /><>{DAYS.map((day) => <span key={day} className="text-xs text-crema/40">{day}</span>)}</><span className="self-center text-left text-xs text-crema/65">Full</span>{DAYS.map((_, day) => <DayButton key={day} selected={fullDays.includes(day)} onClick={() => toggleDay("full", day)} />)}<span className="self-center text-left text-xs text-crema/65">Diferencial</span>{DAYS.map((_, day) => <DayButton key={day} selected={differentialDays.includes(day)} onClick={() => toggleDay("differential", day)} />)}</div>
        </div>
        <div className="mt-5"><div className="mb-2 flex items-center justify-between"><span className="text-[10px] uppercase tracking-wider text-crema/35">Bases de datos</span><button type="button" onClick={loadCatalog} disabled={!sqlProfileId} className="flex items-center gap-1.5 text-[10px] text-arcilla disabled:opacity-35">{catalogJobId && catalog.data?.status !== "completed" && catalog.data?.status !== "failed" ? <Loader2 size={11} className="animate-spin" /> : null} Consultar agente</button></div>{available.length ? <div className="max-h-44 overflow-y-auto rounded-[0.75rem] border border-musgo/20 p-1">{available.map((database) => { const selected = databases.includes(database); return <button key={database} type="button" onClick={() => setDatabases(selected ? databases.filter((item) => item !== database) : [...databases, database])} className="flex w-full items-center gap-2 rounded-[0.5rem] px-3 py-2 text-left font-mono text-xs text-crema/60 hover:bg-musgo/10"><span className={selected ? "grid h-3.5 w-3.5 place-items-center rounded-sm bg-arcilla text-carbon" : "h-3.5 w-3.5 rounded-sm border border-musgo/35"}>{selected ? <Check size={9} /> : null}</span>{database}</button>; })}</div> : <div className="rounded-[0.75rem] border border-musgo/15 p-4 text-xs text-crema/30">Consulte el agente para elegir las bases.</div>}</div>
        <p className="mt-4 text-xs text-crema/40">{fullDays.length ? planSummary({ fullDays, differentialDays }) : "Seleccione al menos un día Full."}</p>
        <p className="mt-1 text-[10px] text-crema/25">Si un Diferencial no tiene Full previo válido, se ejecutará automáticamente un Full inicial.</p>
        {error ? <p className="mt-3 text-xs text-red-400">{error}</p> : null}
        <button type="button" onClick={save} disabled={!fullDays.length || !databases.length || !sqlProfileId || create.isPending} className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-[0.625rem] bg-arcilla text-xs font-medium text-carbon disabled:opacity-35">{create.isPending ? <Loader2 size={13} className="animate-spin" /> : <CalendarDays size={13} />} Guardar plan semanal</button>
      </section>
    </div>
  );
}

function DayButton({ selected, onClick }: { selected: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={selected} onClick={onClick} className={selected ? "mx-auto grid h-8 w-8 place-items-center rounded-[0.5rem] border border-arcilla/40 bg-arcilla/15 text-arcilla" : "mx-auto grid h-8 w-8 place-items-center rounded-[0.5rem] border border-musgo/25 text-crema/25 hover:border-arcilla/25"}>{selected ? <Check size={12} /> : null}</button>;
}
