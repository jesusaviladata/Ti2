"use client";

import { Check, Database, X } from "lucide-react";
import Link from "next/link";
import { useBackupAgentJob, useBackupStatuses } from "@/hooks/useBackups";
import { cn } from "@/lib/utils";
import { useBackupProgressStore } from "@/store/backup-progress.store";
import type { BackupRecord } from "@/types/backup";

function getAgentProgress(job?: {
  status: string;
  phase: string;
  processedUnits: number;
  totalUnits: number;
}, backups: BackupRecord[] = []) {
  if (!job) return { percent: 6, label: "Conectando…", done: false, failed: false };
  const total = Math.max(1, job.totalUnits);
  if (job.status === "completed") return { percent: 100, label: "Backup completado", done: true, failed: false };
  if (job.status === "failed" || job.status === "cancelled") {
    const bakReady = backups.length > 0 && backups.every((backup) => backup.status === "completed");
    return { percent: 100, label: bakReady ? "Entrega fallida" : "Backup fallido", done: true, failed: true };
  }
  if (job.phase === "compressing") return { percent: 86, label: "Creando ZIP…", done: false, failed: false };
  if (job.phase === "archive_ready") return { percent: 91, label: "ZIP validado…", done: false, failed: false };
  if (job.phase === "transferring") return { percent: 96, label: "Enviando al destino…", done: false, failed: false };
  if (job.phase === "cleaning_up") return { percent: 99, label: "Liberando temporales…", done: false, failed: false };
  if (["backing_up", "creating_bak", "validating_bak", "backup_ready"].includes(job.phase)) {
    const completed = Math.min(job.processedUnits, total);
    const phaseFraction = job.phase === "validating_bak" ? 0.75 : job.phase === "backup_ready" ? 1 : 0.25;
    const activeBase = Math.min(completed + 1, total);
    const label = job.phase === "validating_bak"
      ? `Validando base ${activeBase} de ${total}`
      : job.phase === "backup_ready"
        ? `${completed} de ${total} .BAK validados`
        : `Creando .BAK ${activeBase} de ${total}`;
    return {
      percent: Math.min(80, Math.max(10, Math.round(10 + ((completed + phaseFraction) / total) * 70))),
      label,
      done: false,
      failed: false,
    };
  }
  return { percent: 6, label: "En espera…", done: false, failed: false };
}

export function BackupBackgroundIndicator({ collapsed }: { collapsed: boolean }) {
  const batch = useBackupProgressStore((state) => state.activeBatch);
  const dismiss = useBackupProgressStore((state) => state.dismissBackground);
  const { data: job } = useBackupAgentJob(batch?.jobId);
  const backupQueries = useBackupStatuses(batch?.backupIds ?? []);
  const backups = backupQueries.flatMap((query) => query.data ? [query.data] : []);

  if (!batch) return null;

  const finished = backups.filter((backup) => backup.status === "completed" || backup.status === "failed").length;
  const failedCount = backups.filter((backup) => backup.status === "failed").length;
  const total = Math.max(1, batch.backupIds.length || batch.databaseNames.length);
  const directDone = batch.backupIds.length > 0 && finished === batch.backupIds.length;
  const progress = batch.submissionError
    ? { percent: 100, label: "No se pudo iniciar", done: true, failed: true }
    : batch.jobId
      ? getAgentProgress(job, backups)
      : batch.backupIds.length === 0
        ? { percent: 6, label: "Preparando…", done: false, failed: false }
        : {
        percent: directDone ? 100 : Math.max(6, Math.round((finished / total) * 100)),
        label: directDone
          ? failedCount ? "Backup fallido" : "Backup completado"
          : `Base ${Math.min(finished + 1, total)} de ${total}`,
        done: directDone,
        failed: directDone && failedCount > 0,
      };

  if (collapsed) {
    return (
      <div className="px-1 pb-2" title={`${progress.label} · ${progress.percent}%`}>
        <Link
          href="/dashboard/backups"
          className="flex h-10 items-center justify-center rounded-[0.75rem] border border-arcilla/20 bg-arcilla/10"
        >
          {progress.done && !progress.failed
            ? <Check size={16} className="text-green-400" />
            : <Database size={16} className={progress.failed ? "text-red-400" : "text-arcilla"} />}
        </Link>
        <div className="mt-1 h-1 overflow-hidden rounded-full bg-musgo/25">
          <div
            className={cn("h-full transition-[width] duration-700", progress.failed ? "bg-red-500" : progress.done ? "bg-green-500" : "bg-arcilla")}
            style={{ width: `${progress.percent}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mb-2 rounded-[0.85rem] border border-arcilla/20 bg-arcilla/[0.07] p-3">
      <div className="mb-2 flex items-start gap-2">
        <Link href="/dashboard/backups" className="min-w-0 flex-1">
          <p className="font-mono text-[9px] uppercase tracking-wider text-crema/30">Backup en segundo plano</p>
          <p className={cn("mt-0.5 truncate text-xs", progress.failed ? "text-red-400" : progress.done ? "text-green-400" : "text-crema/75")}>{progress.label}</p>
        </Link>
        {progress.done ? (
          <button type="button" onClick={dismiss} aria-label="Ocultar progreso" className="text-crema/30 hover:text-crema">
            <X size={13} />
          </button>
        ) : (
          <span className="font-mono text-[10px] tabular-nums text-arcilla">{progress.percent}%</span>
        )}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-musgo/25">
        <div
          className={cn("h-full rounded-full transition-[width] duration-700", progress.failed ? "bg-red-500" : progress.done ? "bg-green-500" : "bg-arcilla")}
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <p className="mt-1.5 truncate font-mono text-[9px] text-crema/25">
        {batch.submissionError ?? `${batch.databaseNames.length} base${batch.databaseNames.length !== 1 ? "s" : ""}`}
      </p>
    </div>
  );
}
