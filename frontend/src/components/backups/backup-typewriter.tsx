"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FolderOpen } from "lucide-react";
import { useBackupStatus } from "@/hooks/useBackups";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import type { BackupStatus } from "@/types/backup";

const MESSAGES: Record<BackupStatus, string[]> = {
  pending:   ["Esperando turno en la cola...", "Preparando conexión a SQL Server..."],
  running:   [
    "Conectando a SQL Server...",
    "Iniciando BACKUP DATABASE...",
    "Escribiendo datos al disco...",
    "Aplicando compresión...",
    "Verificando integridad...",
    "Finalizando escritura...",
  ],
  completed: ["Backup completado exitosamente.", "Hash SHA-256 calculado.", "Archivo verificado."],
  failed:    ["Error durante la ejecución.", "Revisa los logs para más detalles."],
};

export function BackupTypewriter({ backupId }: { backupId: string }) {
  const { data: backup } = useBackupStatus(backupId);
  const [lines, setLines]     = useState<string[]>([]);
  const [cursor, setCursor]   = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Blink cursor
  useEffect(() => {
    const t = setInterval(() => setCursor((v) => !v), 530);
    return () => clearInterval(t);
  }, []);

  // Add status messages as typewriter lines
  useEffect(() => {
    if (!backup) return;
    const msgs = MESSAGES[backup.status] ?? [];

    msgs.forEach((msg, i) => {
      setTimeout(() => {
        setLines((prev) => {
          if (prev.includes(msg)) return prev;
          return [...prev, msg];
        });
      }, i * 600);
    });

    if (backup.status === "completed") {
      setTimeout(() => {
        setLines((prev) => [
          ...prev,
          backup.fileSizeBytes ? `Tamaño: ${formatBytes(backup.fileSizeBytes)}` : "",
          backup.sha256Hash    ? `SHA-256: ${backup.sha256Hash.slice(0, 16)}...` : "",
          backup.durationSecs  ? `Duración: ${backup.durationSecs}s` : "",
          backup.filePath      ? `Guardado en: ${backup.filePath}` : "",
        ].filter(Boolean));
      }, msgs.length * 600 + 200);
    }

    if (backup.status === "failed" && backup.errorMessage) {
      setTimeout(() => {
        setLines((prev) => [...prev, `Error: ${backup.errorMessage}`]);
      }, 800);
    }
  }, [backup?.status]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <>
    <div className="rounded-[1rem] bg-black/40 border border-musgo/30 p-4 font-sans text-xs text-crema min-h-[140px] max-h-64 overflow-y-auto">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-musgo/20">
        <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
        <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
        <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
        <span className="ml-2 text-subtle text-xs">infra-platform — backup log</span>
      </div>

      {lines.map((line, i) => (
        <div key={i} className={cn(
          "leading-relaxed",
          line.startsWith("Error")       ? "text-danger" :
          line.startsWith("Guardado en") ? "text-yellow-300/90" :
          line.startsWith("SHA") || line.startsWith("Tamaño") || line.startsWith("Duración") ? "text-success" :
          "text-muted"
        )}>
          <span className="text-arcilla/60 select-none">$ </span>{line}
        </div>
      ))}

      {(backup?.status === "pending" || backup?.status === "running") && (
        <div className="text-muted">
          <span className="text-arcilla/60 select-none">$ </span>
          <span className={cursor ? "opacity-100" : "opacity-0"}>▋</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>

    {backup?.status === "completed" && backup.filePath && (
      <div className="mt-3 rounded-[0.875rem] border border-green-700/40 bg-success/10 px-4 py-3 flex items-start gap-3">
        <CheckCircle2 size={15} className="text-success shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-sans text-xs text-success uppercase tracking-wider mb-1">
            Backup guardado en el servidor
          </p>
          <p className="font-sans text-xs text-success break-all leading-relaxed">
            {backup.filePath}
          </p>
        </div>
        <FolderOpen size={14} className="text-success shrink-0 mt-0.5" />
      </div>
    )}
    </>
  );
}
