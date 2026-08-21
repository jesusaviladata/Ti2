"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentStorageService } from "@/services/agent-storage.service";


export const AGENT_STORAGE_KEYS = {
  inventory: ["agent-storage", "inventory"] as const,
  alerts: ["agent-storage", "alerts"] as const,
};

export function useAgentStorage() {
  return useQuery({
    queryKey: AGENT_STORAGE_KEYS.inventory,
    queryFn: agentStorageService.inventory,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useAgentStorageAlerts() {
  return useQuery({
    queryKey: AGENT_STORAGE_KEYS.alerts,
    queryFn: () => agentStorageService.alerts("open"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useUpdateAgentStoragePreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, volumeKey }: { agentId: string; volumeKey: string }) =>
      agentStorageService.updatePreference(agentId, volumeKey),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGENT_STORAGE_KEYS.inventory }),
  });
}

export function useClearAgentStoragePreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: agentStorageService.clearPreference,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGENT_STORAGE_KEYS.inventory }),
  });
}
