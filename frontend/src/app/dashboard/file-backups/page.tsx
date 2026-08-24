"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  FolderSync,
  Loader2,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useFileBackupRuns, useFileBackupTasks, useStartFileBackup } from "@/hooks/useFileBackups";
import { formatBytes } from "@/lib/utils";
import type { FileBackupRun, FileBackupTask } from "@/types/file-backup";

const DAY = ["L", "M", "Mi", "J", "V", "S", "D"];

export default function FileBackupsPage() {
  const tasks = useFileBackupTasks();
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-musgo/25 pb-5">
        <div>
          <p className="mb-1 text-xs uppercase tracking-[0.18em] text-arcilla">Protección de archivos</p>
          <h1 className="font-title text-4xl font-semibold text-crema">Copias de carpetas<span className="text-arcilla">.</span></h1>
          <p className="mt-2 max-w-2xl text-sm text-crema/40">Confirma qué carpetas están protegidas, dónde se guardan y si la última copia quedó verificada.</p>
        </div>
      </header>

      {tasks.isLoading ? <State icon={<Loader2 className="animate-spin" size={20} />} text="Consultando tareas del agente…" /> : null}
      {tasks.isError ? <State icon={<AlertTriangle size={20} />} text="No fue posible consultar las tareas de archivos." danger /> : null}
      {tasks.data?.items.length === 0 ? <State icon={<FolderSync size={22} />} text="Aún no hay carpetas protegidas. La creación guiada se habilitará cuando el destino y el agente estén aplicados." /> : null}

      {tasks.data?.items.length ? (
        <section className="overflow-hidden rounded-[0.75rem] border border-musgo/25" aria-label="Tareas de protección de archivos">
          <div className="grid grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_150px_150px_36px] gap-4 border-b border-musgo/20 bg-musgo/[0.06] px-4 py-2 text-[10px] uppercase tracking-[0.12em] text-crema/30">
            <span>Qué se respalda</span><span>Dónde se guarda</span><span>Próxima copia</span><span>Estado</span><span />
          </div>
          {tasks.data.items.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              open={expanded === task.id}
              onToggle={() => setExpanded((current) => current === task.id ? null : task.id)}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function TaskRow({ task, open, onToggle }: { task: FileBackupTask; open: boolean; onToggle: () => void }) {
  const runs = useFileBackupRuns(open ? task.id : undefined);
  const start = useStartFileBackup();
  const latest = runs.data?.items[0];
  const schedule = task.schedule.weekdays.map((day) => DAY[day] ?? "?").join("/");

  return (
    <article className="border-b border-musgo/15 last:border-b-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="grid w-full grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_150px_150px_36px] items-center gap-4 px-4 py-4 text-left transition-colors hover:bg-musgo/[0.05] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-arcilla/70">
        <span className="min-w-0"><span className="block truncate text-sm font-medium text-crema/80">{task.name}</span><span className="mt-1 block truncate font-mono text-[10px] text-crema/35">{task.sources.map((source) => source.path).join(" · ")}</span></span>
        <span className="truncate text-xs text-crema/50">Perfil {task.destinationProfileId.slice(0, 8)}</span>
        <span className="text-xs text-crema/50">{schedule} · {task.schedule.localTime}</span>
        <RunState run={latest} active={task.isActive} />
        <span className="text-crema/30">{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</span>
      </button>
      {open ? (
        <div className="border-t border-musgo/15 bg-musgo/[0.035] px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <Journey run={latest} loading={runs.isLoading} />
            <button type="button" onClick={() => start.mutate({ taskId: task.id })} disabled={start.isPending || Boolean(latest && !["completed", "completed_with_warnings", "failed", "cancelled", "retryable"].includes(latest.status))} className="flex h-9 items-center gap-2 rounded-[0.5rem] border border-arcilla/40 px-3 text-xs text-arcilla transition-colors hover:bg-arcilla/10 disabled:cursor-not-allowed disabled:opacity-35">
              {start.isPending ? <Loader2 size={13} className="animate-spin" /> : latest?.status === "retryable" ? <RotateCcw size={13} /> : <Play size={13} />}
              {latest?.status === "retryable" ? "Continuar" : "Copiar ahora"}
            </button>
          </div>
          {latest?.errorMessage ? <p className="mt-3 text-xs text-red-400">{latest.errorMessage}</p> : null}
        </div>
      ) : null}
    </article>
  );
}

function Journey({ run, loading }: { run?: FileBackupRun; loading: boolean }) {
  if (loading) return <span className="flex items-center gap-2 text-xs text-crema/35"><Loader2 size={13} className="animate-spin" /> Cargando historial…</span>;
  if (!run) return <span className="text-xs text-crema/35">Todavía no hay copias. La primera será Full.</span>;
  const copied = run.progressPercent > 0 || ["completed", "completed_with_warnings"].includes(run.status);
  const verified = ["publishing", "completed", "completed_with_warnings"].includes(run.phase) || ["completed", "completed_with_warnings"].includes(run.status);
  const delivered = ["completed", "completed_with_warnings"].includes(run.status);
  return <div><div className="flex items-center gap-2 text-xs"><Step label="Copiado" done={copied} /><Line done={verified} /><Step label="Verificado" done={verified} /><Line done={delivered} /><Step label="Entregado" done={delivered} /></div><p className="mt-2 text-[10px] tabular-nums text-crema/30">{run.progressPercent}% · {run.filesProcessed}/{run.filesTotal ?? "?"} archivos · {formatBytes(run.bytesProcessed)}</p></div>;
}

function Step({ label, done }: { label: string; done: boolean }) { return <span className={done ? "flex items-center gap-1.5 text-green-400" : "flex items-center gap-1.5 text-crema/30"}><span className={done ? "flex h-4 w-4 items-center justify-center rounded-full border border-green-500/50" : "h-4 w-4 rounded-full border border-musgo/50"}>{done ? <Check size={10} /> : null}</span>{label}</span>; }
function Line({ done }: { done: boolean }) { return <span className={done ? "h-px w-8 bg-green-500/50" : "h-px w-8 bg-musgo/40"} />; }
function RunState({ run, active }: { run?: FileBackupRun; active: boolean }) { if (!active) return <span className="text-xs text-crema/30">Pausado</span>; if (!run) return <span className="text-xs text-crema/35">Sin ejecutar</span>; if (["completed", "completed_with_warnings"].includes(run.status)) return <span className="flex items-center gap-1.5 text-xs text-green-400"><ShieldCheck size={13} /> Protegido</span>; if (run.status === "failed") return <span className="flex items-center gap-1.5 text-xs text-red-400"><AlertTriangle size={13} /> Requiere atención</span>; return <span className="flex items-center gap-1.5 text-xs text-arcilla"><Loader2 size={13} className="animate-spin" /> {run.progressPercent}%</span>; }
function State({ icon, text, danger = false }: { icon: React.ReactNode; text: string; danger?: boolean }) { return <div className={danger ? "flex items-center justify-center gap-3 rounded-[0.75rem] border border-red-500/25 px-6 py-12 text-sm text-red-400" : "flex items-center justify-center gap-3 rounded-[0.75rem] border border-musgo/25 px-6 py-12 text-sm text-crema/40"}>{icon}{text}</div>; }
