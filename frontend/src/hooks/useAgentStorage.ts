"use client";

import { useQuery } from "@tanstack/react-query";
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
