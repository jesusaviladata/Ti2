import api from "@/lib/api";
import type {
  AgentConfiguration,
  AgentJob,
  AgentProfiles,
  AgentRecord,
} from "@/types/agent";

export const agentsService = {
  list: () =>
    api.get<{ items: AgentRecord[]; total: number }>("/api/v1/agents").then((response) => response.data),

  profiles: (agentId: string) =>
    api.get<AgentProfiles>(`/api/v1/agents/${agentId}/profiles`).then((response) => response.data),

  pairingCode: () =>
    api.post<{ code: string; expiresAt: string }>("/api/v1/agents/pairing-codes").then((response) => response.data),

  createDatabaseCatalog: (agentId: string, sqlProfileId: string) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/database-catalogs`, { sqlProfileId }).then((response) => response.data),

  validateRoot: (agentId: string, root: string) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/validate`, {
      root,
      targetFolders: ["Log", "LogSec", "LogsRadian", "Respuesta"],
      targetFiles: ["BD_log.txt"],
    }).then((response) => response.data),

  saveConfiguration: (
    agentId: string,
    body: { name: string; root: string; validationJobId: string; serverId?: string },
  ) =>
    api.put<AgentConfiguration>(`/api/v1/agents/${agentId}/configuration`, {
      ...body,
      targetFolders: ["Log", "LogSec", "LogsRadian", "Respuesta"],
      targetFiles: ["BD_log.txt"],
    }).then((response) => response.data),

  job: <T = Record<string, unknown>>(jobId: string) =>
    api.get<AgentJob<T>>(`/api/v1/agents/jobs/${jobId}`).then((response) => response.data),
};
