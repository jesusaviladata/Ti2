"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cleanupService } from "@/services/cleanup.service";

const K = {
  folders:   ["cleanup", "folders"]  as const,
  rules:     ["cleanup", "rules"]    as const,
  scan:      (fid?: string) => ["cleanup", "scan", fid ?? "all"] as const,
  trash:     ["cleanup", "trash"]    as const,
  history:   (skip: number) => ["cleanup", "history", skip] as const,
  schedules: ["cleanup", "schedules"] as const,
};

export function useCleanupFolders() {
  return useQuery({ queryKey: K.folders, queryFn: cleanupService.listFolders });
}

export function useCleanupRules() {
  return useQuery({ queryKey: K.rules, queryFn: cleanupService.listRules });
}

export function useScan(folderId?: string, enabled = true) {
  return useQuery({
    queryKey: K.scan(folderId),
    queryFn:  () => cleanupService.scan(folderId),
    enabled,
    staleTime: 30_000,
  });
}

export function useTrash() {
  return useQuery({ queryKey: K.trash, queryFn: cleanupService.listTrash });
}

export function useCleanupHistory(skip = 0) {
  return useQuery({
    queryKey: K.history(skip),
    queryFn:  () => cleanupService.listHistory(skip),
  });
}

export function useCleanupSchedules() {
  return useQuery({ queryKey: K.schedules, queryFn: cleanupService.listSchedules });
}

export function useAddFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.addFolder,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.folders }),
  });
}

export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.deleteFolder,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.folders }),
  });
}

export function useCreateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.createRule,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.rules }),
  });
}

export function useDeleteRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.deleteRule,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.rules }),
  });
}

export function useExecuteCleanup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ paths, ruleId }: { paths: string[]; ruleId?: string }) =>
      cleanupService.execute(paths, ruleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cleanup", "scan"] });
      qc.invalidateQueries({ queryKey: K.trash });
      qc.invalidateQueries({ queryKey: ["cleanup", "history"] });
    },
  });
}

export function usePermanentDelete() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.permanentDelete,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.trash }),
  });
}

export function useRestore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.restore,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.trash }),
  });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.createSchedule,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.schedules }),
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cleanupService.deleteSchedule,
    onSuccess:  () => qc.invalidateQueries({ queryKey: K.schedules }),
  });
}
