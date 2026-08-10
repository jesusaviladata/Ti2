import { cn } from "@/lib/utils";
import type { BackupStatus } from "@/types/backup";

const CONFIG: Record<BackupStatus, { label: string; classes: string; dot?: string }> = {
  pending:   { label: "Pendiente",  classes: "bg-musgo/20 text-crema/50  border-musgo/30",    dot: "bg-crema/30" },
  running:   { label: "Ejecutando", classes: "bg-arcilla/10 text-arcilla border-arcilla/30",   dot: "bg-arcilla animate-pulse" },
  completed: { label: "Completado", classes: "bg-green-900/20 text-green-400 border-green-800/30", dot: "bg-green-400" },
  failed:    { label: "Fallido",    classes: "bg-red-900/20 text-red-400 border-red-800/30",   dot: "bg-red-400" },
};

export function BackupStatusBadge({ status }: { status: BackupStatus }) {
  const cfg = CONFIG[status] ?? CONFIG.pending;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono border", cfg.classes)}>
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />
      {cfg.label}
    </span>
  );
}
