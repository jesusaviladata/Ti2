"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fileBackupsService } from "@/services/file-backups.service";
import type { FileBackupRunStatus, FileBackupStrategy } from "@/types/file-backup";

const TERMINAL = new Set<FileBackupRunStatus>([
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
]);

export const FILE_BACKUP_KEYS = {
  all: ["file-backups"] as const,
  tasks: ["file-backups", "tasks"] as const,
  runs: (taskId: string) => ["file-backups", "runs", taskId] as const,
};

export function useFileBackupTasks() {
  return useQuery({
    queryKey: FILE_BACKUP_KEYS.tasks,
    queryFn: () => fileBackupsService.listTasks(),
    staleTime: 30_000,
  });
}

export function useFileBackupRuns(taskId?: string) {
  return useQuery({
    queryKey: FILE_BACKUP_KEYS.runs(taskId ?? ""),
    queryFn: () => fileBackupsService.listRuns(taskId!),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const running = query.state.data?.items.some((item) => !TERMINAL.has(item.status));
      return running ? 2_000 : false;
    },
  });
}

export function useStartFileBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, strategy }: { taskId: string; strategy?: FileBackupStrategy }) =>
      fileBackupsService.startRun(taskId, strategy),
    onSuccess: (_run, variables) => {
      void client.invalidateQueries({ queryKey: FILE_BACKUP_KEYS.runs(variables.taskId) });
    },
  });
}
