"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentsService } from "@/services/agents.service";
import type { AgentJob } from "@/types/agent";

export const AGENT_KEYS = {
  all: ["agents"] as const,
  profiles: (agentId: string) => ["agents", agentId, "profiles"] as const,
  job: (jobId: string) => ["agent-jobs", jobId] as const,
};

export function useAgents() {
  return useQuery({ queryKey: AGENT_KEYS.all, queryFn: agentsService.list, refetchInterval: 30_000 });
}

export function useAgentProfiles(agentId: string | null) {
  return useQuery({
    queryKey: AGENT_KEYS.profiles(agentId ?? "none"),
    queryFn: () => agentsService.profiles(agentId!),
    enabled: Boolean(agentId),
  });
}

export function useAgentJob<T = Record<string, unknown>>(jobId: string | null) {
  return useQuery<AgentJob<T>>({
    queryKey: AGENT_KEYS.job(jobId ?? "none"),
    queryFn: () => agentsService.job<T>(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["completed", "failed", "cancelled"].includes(status) ? false : 1_500;
    },
  });
}

export function usePairingCode() {
  return useMutation({ mutationFn: agentsService.pairingCode });
}

export function useValidateAgentRoot() {
  return useMutation({ mutationFn: ({ agentId, root }: { agentId: string; root: string }) => agentsService.validateRoot(agentId, root) });
}

export function useSaveAgentConfiguration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, ...body }: { agentId: string; name: string; root: string; validationJobId: string; serverId?: string }) =>
      agentsService.saveConfiguration(agentId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGENT_KEYS.all }),
  });
}

export function useSelectedAgentId(agents: { id: string; online: boolean }[] | undefined) {
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const online = (agents ?? []).filter((agent) => agent.online);
    if (!online.some((agent) => agent.id === selected)) {
      setSelected(online[0]?.id ?? null);
    }
  }, [agents, selected]);
  return [selected, setSelected] as const;
}
