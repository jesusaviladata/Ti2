"use client";

import { useQuery, useQueries, useMutation, useQueryClient } from "@tanstack/react-query";
import { backupsService } from "@/services/backups.service";
import type { ConnectionPayload } from "@/types/connection";

export const BACKUP_KEYS = {
  all:       ["backups"] as const,
  list:      (skip = 0, limit = 50) => ["backups", "list", skip, limit] as const,
  status:    (id: string) => ["backups", "status", id] as const,
  databases: (connId?: string) => ["backups", "databases", connId ?? "env"] as const,
  agents:    ["backups", "agents"] as const,
  agentDatabases: (agentId?: string, profileId?: string) => ["backups", "agent-databases", agentId, profileId] as const,
  agentJob: (jobId?: string) => ["backups", "agent-job", jobId] as const,
  agentPlans: ["backups", "agent-plans"] as const,
};

export function useBackupList(skip = 0, limit = 50) {
  return useQuery({
    queryKey: BACKUP_KEYS.list(skip, limit),
    queryFn:  () => backupsService.listBackups(skip, limit),
    refetchInterval: 5000,
  });
}

export function useBackupAgents(enabled = true) {
  return useQuery({
    queryKey: BACKUP_KEYS.agents,
    queryFn: () => backupsService.listAgents(),
    enabled,
    refetchInterval: 30_000,
  });
}

export function useAgentDatabases(agentId?: string, sqlProfileId?: string, enabled = true) {
  return useQuery({
    queryKey: BACKUP_KEYS.agentDatabases(agentId, sqlProfileId),
    queryFn: () => backupsService.listAgentDatabases(agentId!, sqlProfileId!),
    enabled: enabled && !!agentId && !!sqlProfileId,
    staleTime: 60_000,
  });
}

export function useBackupAgentJob(jobId?: string) {
  return useQuery({
    queryKey: BACKUP_KEYS.agentJob(jobId),
    queryFn: () => backupsService.getAgentJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" || status === "cancelled"
        ? false
        : 1000;
    },
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

export function useBackupStatuses(backupIds: string[]) {
  return useQueries({
    queries: backupIds.map((backupId) => ({
      queryKey: BACKUP_KEYS.status(backupId),
      queryFn: () => backupsService.getStatus(backupId),
      refetchInterval: (query: any) => {
        const status = query.state.data?.status;
        return status === "running" || status === "pending" ? 1000 : false;
      },
    })),
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
  return useQuery({
    queryKey: BACKUP_KEYS.agentPlans,
    queryFn: () => backupsService.listAgentPlans(),
    refetchInterval: 30_000,
  });
}

export function useCreateAgentBackupPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.createAgentPlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.agentPlans }),
  });
}

export function useUpdateAgentBackupPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: Parameters<typeof backupsService.updateAgentPlan>[1] }) =>
      backupsService.updateAgentPlan(planId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.agentPlans }),
  });
}

export function useDeleteAgentBackupPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backupsService.deleteAgentPlan,
    onSuccess: () => qc.invalidateQueries({ queryKey: BACKUP_KEYS.agentPlans }),
  });
}
