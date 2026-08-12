"use client";

import { Check, Database, X } from "lucide-react";
import Link from "next/link";
import { useBackupAgentJob, useBackupStatuses } from "@/hooks/useBackups";
import { cn } from "@/lib/utils";
import { useBackupProgressStore } from "@/store/backup-progress.store";

function getAgentProgress(job?: {
  status: string;
  phase: string;
  processedUnits: number;
  totalUnits: number;
}) {
  if (!job) return { percent: 6, label: "Conectando…", done: false, failed: false };
  const total = Math.max(1, job.totalUnits);
  if (job.status === "completed") return { percent: 100, label: "Backup completado", done: true, failed: false };
  if (job.status === "failed" || job.status === "cancelled") {
    return { percent: 100, label: "Backup fallido", done: true, failed: true };
  }
  if (job.phase === "compressing") return { percent: 88, label: "Creando ZIP…", done: false, failed: false };
  if (job.phase === "transferring") return { percent: 95, label: "Transfiriendo…", done: false, failed: false };
  if (job.phase === "backing_up") {
    const completed = Math.min(job.processedUnits, total);
    return {
      percent: Math.max(10, Math.round(10 + (completed / total) * 70)),
      label: `Base ${Math.min(completed + 1, total)} de ${total}`,
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
  const progress = batch.jobId
    ? getAgentProgress(job)
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
        {batch.databaseNames.length} base{batch.databaseNames.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}
