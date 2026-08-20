import api from "@/lib/api";
import type { ManagedAgentProfile, ManagedProfileInput } from "@/types/agent-profile";


export const agentProfilesService = {
  list: (agentId: string) =>
    api.get<{ agentId: string; agentOnline: boolean; items: ManagedAgentProfile[]; total: number }>(`/api/v1/agents/${agentId}/managed-profiles`).then((response) => response.data),
  create: (agentId: string, input: ManagedProfileInput) =>
    api.post<ManagedAgentProfile>(`/api/v1/agents/${agentId}/managed-profiles`, input).then((response) => response.data),
  update: (agentId: string, profileId: string, input: ManagedProfileInput) =>
    api.put<ManagedAgentProfile>(`/api/v1/agents/${agentId}/managed-profiles/${profileId}`, input).then((response) => response.data),
  remove: (agentId: string, profileId: string) =>
    api.delete(`/api/v1/agents/${agentId}/managed-profiles/${profileId}`),
  test: (agentId: string, profileId: string) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/managed-profiles/${profileId}/test`).then((response) => response.data),
  discover: (agentId: string) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/managed-profiles/discover`).then((response) => response.data),
};
