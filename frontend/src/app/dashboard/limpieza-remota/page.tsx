"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, FileSearch, Loader2, ShieldCheck, Trash2, WifiOff } from "lucide-react";
import { AgentSelector } from "@/components/agents/agent-selector";
import { useAgentJob, useAgents, useSelectedAgentId } from "@/hooks/useAgents";
import { useExecuteAgentCleanup, useSimulateAgentCleanup } from "@/hooks/useAgentCleanup";
import { formatBytes } from "@/lib/utils";
import type { CleanupExecutionResult, CleanupSimulationResult } from "@/types/agent";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function apiMessage(error: unknown, fallback: string) {
  const candidate = error as { response?: { data?: { detail?: string | { message?: string }; error?: { message?: string } } }; message?: string };
  const detail = candidate.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  return candidate.response?.data?.error?.message ?? candidate.message ?? fallback;
}

function PhaseRail({ phase }: { phase: "simulate" | "review" | "confirm" | "done" }) {
  const phases = [
    ["simulate", "Simular"], ["review", "Revisar"], ["confirm", "Confirmar"], ["done", "Resultado"],
  ] as const;
  const current = phases.findIndex(([id]) => id === phase);
  return (
    <ol className="grid grid-cols-4 overflow-hidden rounded-[0.875rem] border border-musgo/20 bg-musgo/[0.04]">
      {phases.map(([id, label], index) => (
        <li key={id} className="flex min-h-14 items-center gap-2 border-r border-musgo/15 px-3 last:border-r-0">
          <span className={index < current ? "grid h-5 w-5 place-items-center rounded-full bg-green-500/15 text-green-400" : index === current ? "grid h-5 w-5 place-items-center rounded-full border border-arcilla/45 bg-arcilla/10 text-arcilla" : "grid h-5 w-5 place-items-center rounded-full border border-musgo/25 text-crema/25"}>
            {index < current ? <Check size={11} /> : index + 1}
          </span>
          <span className={index <= current ? "text-xs text-crema/70" : "text-xs text-crema/25"}>{label}</span>
        </li>
      ))}
    </ol>
  );
}

export default function LimpiezaRemotaPage() {
  const agentsQuery = useAgents();
  const agents = agentsQuery.data?.items ?? [];
  const [agentId, setAgentId] = useSelectedAgentId(agents);
  const selected = agents.find((agent) => agent.id === agentId) ?? null;
  const simulate = useSimulateAgentCleanup();
  const execute = useExecuteAgentCleanup();
  const [simulationJobId, setSimulationJobId] = useState<string | null>(null);
  const [executionJobId, setExecutionJobId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const simulation = useAgentJob<CleanupSimulationResult>(simulationJobId);
  const execution = useAgentJob<CleanupExecutionResult>(executionJobId);

  useEffect(() => {
    setSimulationJobId(null);
    setExecutionJobId(null);
    setConfirmed(false);
    setLocalError(null);
  }, [agentId]);

  const simulationResult = simulation.data?.status === "completed" ? simulation.data.result : null;
  const executionResult = execution.data?.status === "completed" ? execution.data.result : null;
  const phase = useMemo(() => {
    if (executionJobId) return executionResult ? "done" : "confirm";
    if (simulationResult) return confirmed ? "confirm" : "review";
    if (simulationJobId) return "simulate";
    return "simulate";
  }, [confirmed, executionJobId, executionResult, simulationJobId, simulationResult]);
  const busySimulation = Boolean(simulationJobId && (!simulation.data || !TERMINAL.has(simulation.data.status)));
  const busyExecution = Boolean(executionJobId && (!execution.data || !TERMINAL.has(execution.data.status)));

  async function startSimulation() {
    if (!agentId) return;
    setLocalError(null);
    setConfirmed(false);
    setExecutionJobId(null);
    try {
      const result = await simulate.mutateAsync(agentId);
      setSimulationJobId(result.jobId);
    } catch (error) {
      setLocalError(apiMessage(error, "No fue posible iniciar la simulación."));
    }
  }

  async function startExecution() {
    if (!simulationJobId || !confirmed) return;
    setLocalError(null);
    try {
      const result = await execute.mutateAsync(simulationJobId);
      setExecutionJobId(result.jobId);
    } catch (error) {
      setLocalError(apiMessage(error, "No fue posible iniciar la limpieza."));
    }
  }

  const error = localError ?? simulation.data?.error ?? execution.data?.error;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-xs uppercase tracking-[0.18em] text-arcilla">Agentes</p>
          <h1 className="font-title text-4xl font-semibold text-crema">Limpieza<span className="text-arcilla">.</span></h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-9 items-center gap-2 rounded-full border border-arcilla/25 bg-arcilla/[0.07] px-3 text-[11px] text-arcilla/80"><ShieldCheck size={12} /> Simular → revisar → confirmar</span>
          <AgentSelector agents={agents} value={agentId} onChange={setAgentId} />
        </div>
      </header>

      <PhaseRail phase={phase} />

      {!agents.some((agent) => agent.online) ? (
        <section className="rounded-[1.25rem] border border-musgo/20 bg-musgo/[0.06] p-10 text-center">
          <WifiOff size={23} className="mx-auto mb-3 text-crema/20" />
          <p className="text-sm text-crema/55">No hay agentes conectados</p>
          <p className="mt-1 text-xs text-crema/30">Los desconectados siguen visibles en Configuración → Agentes, pero no pueden ejecutar operaciones.</p>
        </section>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-[1.25rem] border border-musgo/20 bg-musgo/[0.06] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium text-crema/75">Alcance protegido</h2>
                <p className="mt-1 text-xs leading-relaxed text-crema/35">Se vacían archivos; las carpetas y subcarpetas siempre se conservan.</p>
              </div>
              <span className="rounded-full border border-musgo/25 px-2.5 py-1 font-mono text-[10px] text-crema/40">Manual</span>
            </div>
            <div className="mt-5 rounded-[0.875rem] border border-musgo/20 bg-carbon/25 p-4">
              <p className="truncate font-mono text-xs text-crema/65">{selected?.configuration?.root ?? "Raíz sin configurar"}</p>
              <p className="mt-2 font-mono text-[10px] leading-5 text-crema/35">Propiedad\core\Log<br />Propiedad\core\LogSec<br />Propiedad\core\LogsRadian<br />Propiedad\core\Respuesta<br />Propiedad\core\BD_log.txt</p>
            </div>

            {simulationResult ? (
              <div className="mt-5 space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Metric label="Propiedades" value={simulationResult.propertiesProcessed} />
                  <Metric label="Afectadas" value={simulationResult.propertiesAffected} />
                  <Metric label="Archivos" value={simulationResult.eligibleCount} accent />
                  <Metric label="A liberar" value={formatBytes(simulationResult.bytesEligible)} accent />
                </div>
                {simulationResult.truncated ? <p className="flex items-center gap-2 text-xs text-amber-400"><AlertTriangle size={13} /> La simulación alcanzó el límite de seguridad; revise antes de continuar.</p> : null}
                {simulationResult.samples.length ? (
                  <div className="max-h-64 overflow-auto rounded-[0.75rem] border border-musgo/15">
                    {simulationResult.samples.map((item) => <div key={item.relativePath} className="flex items-center justify-between gap-4 border-b border-musgo/10 px-3 py-2 last:border-b-0"><span className="min-w-0 truncate font-mono text-[10px] text-crema/45">{item.relativePath}</span><span className="shrink-0 text-[10px] text-crema/30">{formatBytes(item.sizeBytes)}</span></div>)}
                  </div>
                ) : <p className="rounded-[0.75rem] border border-green-500/15 bg-green-500/[0.05] p-4 text-sm text-green-400/80">No hay archivos que limpiar.</p>}
              </div>
            ) : null}

            {executionResult ? (
              <div className={executionResult.failedCount ? "mt-5 rounded-[0.875rem] border border-amber-500/20 bg-amber-500/[0.06] p-4" : "mt-5 rounded-[0.875rem] border border-green-500/20 bg-green-500/[0.06] p-4"}>
                <p className="text-sm font-medium text-crema/75">Limpieza finalizada</p>
                <p className="mt-1 text-xs text-crema/45">{executionResult.deletedCount} archivos eliminados · {formatBytes(executionResult.bytesDeleted)} liberados · {executionResult.failedCount} fallidos</p>
              </div>
            ) : null}
          </section>

          <aside className="self-start rounded-[1.25rem] border border-musgo/20 bg-musgo/[0.06] p-5">
            <h2 className="text-sm font-medium text-crema/75">Operación</h2>
            <p className="mt-1 text-xs leading-relaxed text-crema/35">La simulación no modifica archivos. La ejecución elimina directamente sólo el manifiesto revisado.</p>
            {!simulationResult ? (
              <button type="button" onClick={startSimulation} disabled={!selected?.configuration || simulate.isPending || busySimulation} className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-[0.625rem] border border-arcilla/30 bg-arcilla/10 text-xs text-arcilla hover:bg-arcilla/15 disabled:opacity-35">
                {simulate.isPending || busySimulation ? <><Loader2 size={13} className="animate-spin" /> Simulando…</> : <><FileSearch size={13} /> Simular limpieza</>}
              </button>
            ) : simulationResult.eligibleCount > 0 && !executionResult ? (
              <div className="mt-5 space-y-3">
                <label className="flex cursor-pointer items-start gap-2 rounded-[0.625rem] border border-musgo/20 p-3">
                  <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-0.5 accent-[#38bdf8]" />
                  <span className="text-xs leading-relaxed text-crema/50">Confirmo eliminar permanentemente los {simulationResult.eligibleCount} archivos revisados. Las carpetas se conservarán.</span>
                </label>
                <button type="button" onClick={startExecution} disabled={!confirmed || execute.isPending || busyExecution} className="flex h-10 w-full items-center justify-center gap-2 rounded-[0.625rem] border border-red-500/30 bg-red-500/10 text-xs text-red-300 hover:bg-red-500/15 disabled:opacity-35">
                  {execute.isPending || busyExecution ? <><Loader2 size={13} className="animate-spin" /> Limpiando…</> : <><Trash2 size={13} /> Vaciar archivos</>}
                </button>
              </div>
            ) : (
              <button type="button" onClick={startSimulation} className="mt-5 h-10 w-full rounded-[0.625rem] border border-musgo/25 text-xs text-crema/55 hover:border-arcilla/30">Nueva simulación</button>
            )}
            {!selected?.configuration ? <p className="mt-3 text-xs text-amber-400/75">Configure y valide la raíz en Configuración → Agentes.</p> : null}
            {error ? <p className="mt-3 text-xs leading-relaxed text-red-400">{error}</p> : null}
          </aside>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string | number; accent?: boolean }) {
  return <div className="rounded-[0.75rem] border border-musgo/15 bg-carbon/20 p-3"><p className={accent ? "text-xl font-semibold tabular-nums text-arcilla" : "text-xl font-semibold tabular-nums text-crema/80"}>{value}</p><p className="mt-1 text-[10px] uppercase tracking-wider text-crema/30">{label}</p></div>;
}
