"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentProfilesService } from "@/services/agent-profiles.service";
import type { ManagedProfileInput } from "@/types/agent-profile";


export const MANAGED_PROFILE_KEYS = {
  list: (agentId: string) => ["agents", agentId, "managed-profiles"] as const,
};

export function useManagedAgentProfiles(agentId: string | null) {
  return useQuery({
    queryKey: MANAGED_PROFILE_KEYS.list(agentId ?? "none"),
    queryFn: () => agentProfilesService.list(agentId!),
    enabled: Boolean(agentId),
    refetchInterval: 15_000,
  });
}

export function useSaveManagedProfile(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ profileId, input }: { profileId?: string; input: ManagedProfileInput }) =>
      profileId ? agentProfilesService.update(agentId, profileId, input) : agentProfilesService.create(agentId, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MANAGED_PROFILE_KEYS.list(agentId) }),
  });
}

export function useDeleteManagedProfile(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => agentProfilesService.remove(agentId, profileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MANAGED_PROFILE_KEYS.list(agentId) }),
  });
}

export function useTestManagedProfile(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => agentProfilesService.test(agentId, profileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MANAGED_PROFILE_KEYS.list(agentId) }),
  });
}

export function useDiscoverAgentEnvironment(agentId: string) {
  return useMutation({
    mutationFn: () => agentProfilesService.discover(agentId),
  });
}
