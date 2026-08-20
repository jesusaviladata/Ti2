"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FolderLock, Loader2, Play, RotateCcw, Server, Trash2 } from "lucide-react";
import { AgentSelector } from "@/components/agents/agent-selector";
import { useAgentJob, useAgents, useSelectedAgentId } from "@/hooks/useAgents";
import { useExecuteAgentCleanup, useSimulateAgentCleanup } from "@/hooks/useAgentCleanup";
import { formatBytes } from "@/lib/utils";

const TARGETS = ["Log", "LogSec", "LogsRadian", "Respuesta", "BD_log.txt"];

export default function CleanupPage() {
  const agentsQuery = useAgents();
  const agents = agentsQuery.data?.items ?? [];
  const [agentId, setAgentId] = useSelectedAgentId(agents);
  const selected = agents.find((item) => item.id === agentId) ?? null;
  const simulate = useSimulateAgentCleanup();
  const execute = useExecuteAgentCleanup();
  const [simulationJobId, setSimulationJobId] = useState<string | null>(null);
  const [executionJobId, setExecutionJobId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const simulation = useAgentJob<Record<string, any>>(simulationJobId);
  const execution = useAgentJob<Record<string, any>>(executionJobId);

  useEffect(() => {
    setSimulationJobId(null);
    setExecutionJobId(null);
    setConfirmed(false);
  }, [agentId]);

  const result = simulation.data?.status === "completed" ? simulation.data.result : null;
  const completed = execution.data?.status === "completed";
  const phase = executionJobId ? 3 : result ? (confirmed ? 2 : 1) : 0;
  const error = simulation.data?.status === "failed" ? simulation.data.error : execution.data?.status === "failed" ? execution.data.error : null;

  async function startSimulation() {
    if (!agentId) return;
    setExecutionJobId(null);
    setConfirmed(false);
    setSimulationJobId((await simulate.mutateAsync(agentId)).jobId);
  }

  async function startExecution() {
    if (!simulationJobId || !confirmed) return;
    setExecutionJobId((await execute.mutateAsync(simulationJobId)).jobId);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="mb-1 text-xs uppercase tracking-[0.18em] text-arcilla">Servidores Core</p><h1 className="font-title text-4xl font-semibold text-crema">Limpieza<span className="text-arcilla">.</span></h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-crema/40">Una sola operación segura por agente: simular, revisar y vaciar los archivos autorizados. Las carpetas se conservan.</p></div>
        <AgentSelector agents={agents} value={agentId} onChange={setAgentId} />
      </header>

      <div className="grid grid-cols-4 gap-2" aria-label="Fases de limpieza">
        {["Simular", "Revisar", "Confirmar", "Resultado"].map((label, index) => <div key={label} className={index <= phase ? "rounded-[0.625rem] border border-arcilla/30 bg-arcilla/[0.08] px-3 py-2 text-center text-xs text-arcilla" : "rounded-[0.625rem] border border-musgo/20 px-3 py-2 text-center text-xs text-crema/25"}>{index < phase ? "✓ " : ""}{label}</div>)}
      </div>

      {!selected ? <EmptyState text="No hay agentes conectados. Los desconectados siguen visibles en Configuración, pero no pueden operar Limpieza." /> : !selected.configuration ? <EmptyState text="Este agente aún no tiene una raíz fija validada. Ve a Configuración → Agentes → Configurar raíz." /> : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="rounded-[1.1rem] border border-musgo/20 bg-musgo/[0.06] p-5">
            <div className="flex items-start gap-3"><FolderLock size={18} className="mt-0.5 text-arcilla" /><div><p className="text-sm font-medium text-crema/75">Raíz autorizada e inmutable para esta operación</p><p className="mt-1 font-mono text-xs text-crema/45">{selected.configuration.root}</p></div></div>
            <div className="mt-5 rounded-[0.875rem] border border-musgo/20 bg-carbon/40 p-4"><p className="text-xs text-crema/45">Por cada carpeta de propiedad:</p><p className="mt-2 font-mono text-sm text-crema/75">Propiedad\core\</p><div className="mt-3 flex flex-wrap gap-2">{TARGETS.map((target) => <span key={target} className="rounded-[0.5rem] border border-musgo/25 bg-musgo/10 px-2.5 py-1 text-[10px] text-crema/50">{target}</span>)}</div><p className="mt-3 text-[11px] leading-relaxed text-crema/35">Se eliminan todos los archivos internos elegibles. No se elimina ninguna carpeta, no se siguen enlaces y no se aceptan rutas manuales.</p></div>

            {!simulationJobId ? <button type="button" onClick={startSimulation} disabled={simulate.isPending} className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-[0.625rem] bg-arcilla text-xs font-medium text-carbon disabled:opacity-40">{simulate.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Simular limpieza completa</button> : simulation.isLoading || !result ? <ProgressCard label={simulation.data?.phase ?? "Escaneando propiedades"} current={simulation.data?.processedUnits ?? 0} total={simulation.data?.totalUnits ?? 0} /> : (
              <div className="mt-5 space-y-4">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4"><Stat label="Propiedades" value={Number(result.propertiesAffected ?? 0)} /><Stat label="Archivos" value={Number(result.eligibleCount ?? 0)} accent /><Stat label="Espacio" value={formatBytes(Number(result.bytesEligible ?? 0))} accent /><Stat label="Protegidos" value={Number(result.protectedCount ?? 0)} /></div>
                {result.truncated ? <p className="flex items-center gap-2 text-xs text-amber-300"><AlertTriangle size={13} /> La simulación alcanzó su límite de seguridad; no confirme hasta revisarlo.</p> : null}
                {!executionJobId ? <label className="flex cursor-pointer items-start gap-3 rounded-[0.875rem] border border-red-500/25 bg-red-500/[0.04] p-4"><input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span><span className="block text-sm text-red-300">Confirmo la eliminación definitiva</span><span className="mt-1 block text-xs leading-relaxed text-crema/40">Se usarán exactamente el manifiesto y hash de esta simulación. Si algo cambió, el agente rechazará la ejecución.</span></span></label> : null}
                {!executionJobId ? <div className="flex gap-3"><button type="button" onClick={() => setSimulationJobId(null)} className="flex h-10 flex-1 items-center justify-center gap-2 rounded-[0.625rem] border border-musgo/25 text-xs text-crema/45"><RotateCcw size={13} /> Simular de nuevo</button><button type="button" onClick={startExecution} disabled={!confirmed || execute.isPending || Boolean(result.truncated)} className="flex h-10 flex-1 items-center justify-center gap-2 rounded-[0.625rem] bg-red-500 text-xs font-medium text-white disabled:opacity-30"><Trash2 size={13} /> Vaciar archivos</button></div> : completed ? <div className="rounded-[0.875rem] border border-green-500/25 bg-green-500/[0.05] p-4"><p className="flex items-center gap-2 text-sm text-green-300"><CheckCircle2 size={15} /> Limpieza terminada</p><p className="mt-2 text-xs text-crema/40">{Number(execution.data?.result?.deletedCount ?? 0)} archivos eliminados · {formatBytes(Number(execution.data?.result?.bytesDeleted ?? 0))} liberados · {Number(execution.data?.result?.failedCount ?? 0)} errores.</p></div> : <ProgressCard label={execution.data?.phase ?? "Eliminando archivos autorizados"} current={execution.data?.processedUnits ?? 0} total={execution.data?.totalUnits ?? 0} />}
              </div>
            )}
            {error ? <p className="mt-4 rounded-[0.625rem] border border-red-500/25 bg-red-500/[0.05] px-3 py-2 text-xs text-red-400">{error}</p> : null}
          </section>
          <aside className="rounded-[1.1rem] border border-musgo/20 bg-musgo/[0.05] p-5"><div className="flex items-center gap-2"><Server size={15} className="text-arcilla" /><p className="text-sm font-medium text-crema/70">Cómo funciona</p></div><ol className="mt-4 space-y-4 text-xs leading-relaxed text-crema/40"><li><span className="mr-2 text-arcilla">1.</span>El backend toma la raíz validada; el navegador no envía otra ruta.</li><li><span className="mr-2 text-arcilla">2.</span>El agente recorre sólo Propiedad\core y crea un manifiesto con hash.</li><li><span className="mr-2 text-arcilla">3.</span>Usted revisa conteos y espacio antes de confirmar.</li><li><span className="mr-2 text-arcilla">4.</span>El agente revalida cada archivo y elimina únicamente lo aprobado.</li></ol></aside>
        </div>
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) { return <div className="rounded-[1.1rem] border border-musgo/20 bg-musgo/[0.05] p-12 text-center"><FolderLock size={22} className="mx-auto mb-3 text-crema/20" /><p className="text-sm text-crema/45">{text}</p></div>; }
function Stat({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) { return <div className="rounded-[0.75rem] border border-musgo/20 bg-carbon/40 p-3"><p className={accent ? "text-xl font-semibold tabular-nums text-arcilla" : "text-xl font-semibold tabular-nums text-crema/80"}>{value}</p><p className="mt-1 text-[9px] uppercase tracking-wider text-crema/30">{label}</p></div>; }
function ProgressCard({ label, current, total }: { label: string; current: number; total: number }) { const percent = total ? Math.round(current / total * 100) : 8; return <div className="mt-5 rounded-[0.875rem] border border-musgo/20 p-4"><div className="flex items-center justify-between text-xs text-crema/45"><span className="flex items-center gap-2"><Loader2 size={13} className="animate-spin text-arcilla" /> {label}</span><span className="tabular-nums">{current}/{total || "?"}</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-musgo/20"><div className="h-full bg-arcilla transition-[width]" style={{ width: `${percent}%` }} /></div></div>; }
