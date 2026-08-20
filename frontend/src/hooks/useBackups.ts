"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { backupsService } from "@/services/backups.service";
import type { ConnectionPayload } from "@/types/connection";

export const BACKUP_KEYS = {
  all:       ["backups"] as const,
  list:      (skip = 0, limit = 50) => ["backups", "list", skip, limit] as const,
  status:    (id: string) => ["backups", "status", id] as const,
  databases: (connId?: string) => ["backups", "databases", connId ?? "env"] as const,
  plans: ["backups", "plans"] as const,
};

export function useBackupList(skip = 0, limit = 50) {
  return useQuery({
    queryKey: BACKUP_KEYS.list(skip, limit),
    queryFn:  () => backupsService.listBackups(skip, limit),
    refetchInterval: 5000,
  });
}

export function useDatabases(conn?: ConnectionPayload | null, connId?: string, enabled = true) {
  return useQuery({
    queryKey: BACKUP_KEYS.databases(connId),
    queryFn:  conn
      ? () => backupsService.listDatabasesForConnection(conn)
      : ()  => backupsService.listDatabases(),
    staleTime: 60_000,
    enabled,
  });
}

export function useBackupStatus(backupId: string | null) {
  return useQuery({
    queryKey: BACKUP_KEYS.status(backupId ?? ""),
    queryFn:  () => backupsService.getStatus(backupId!),
    enabled:  !!backupId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
  });
}

export function useTriggerBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.triggerBackup,
    onSuccess:  () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.all }),
  });
}

export function useTriggerAgentBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.triggerAgentBackup,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.all }),
  });
}

export function useAgentBackupPlans() {
  return useQuery({ queryKey: BACKUP_KEYS.plans, queryFn: backupsService.listAgentPlans });
}

export function useCreateAgentBackupPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.createAgentPlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.plans }),
  });
}

export function useDeleteAgentBackupPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.deleteAgentPlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.plans }),
  });
}

export function useRetryBackupDelivery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.retryDelivery,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.all }),
  });
}
