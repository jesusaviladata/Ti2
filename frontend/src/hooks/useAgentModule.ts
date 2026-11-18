"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentModuleService } from "@/services/agent-module.service";
import { AGENT_KEYS } from "@/hooks/useAgents";
import { BACKUP_KEYS } from "@/hooks/useBackups";

export const AGENT_MODULE_KEY = ["agent-module"] as const;

export function useAgentModule() {
  return useQuery({ queryKey: AGENT_MODULE_KEY, queryFn: agentModuleService.status });
}

export function useSetAgentModule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: agentModuleService.setEnabled,
    onSuccess: (status) => {
      queryClient.setQueryData(AGENT_MODULE_KEY, status);
      // Lo que dependía del módulo (agentes, planes de backup) debe volver a consultarse.
      queryClient.invalidateQueries({ queryKey: AGENT_KEYS.all });
      queryClient.invalidateQueries({ queryKey: BACKUP_KEYS.all });
    },
  });
}

export function useDownloadBootstrap() {
  return useMutation({ mutationFn: agentModuleService.downloadBootstrap });
}
