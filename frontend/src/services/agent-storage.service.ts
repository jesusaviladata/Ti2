import api from "@/lib/api";
import type { AgentStorageAlert, AgentStorageInventory } from "@/types/agent-storage";


export const agentStorageService = {
  inventory: () =>
    api.get<AgentStorageInventory>("/api/v1/agent-storage").then((response) => response.data),

  alerts: (status: "open" | "resolved" = "open") =>
    api
      .get<{ items: AgentStorageAlert[]; total: number }>("/api/v1/agent-storage/alerts", {
        params: { status },
      })
      .then((response) => response.data),

  updatePreference: (agentId: string, volumeKey: string) =>
    api
      .put("/api/v1/agent-storage/preference", { agentId, volumeKey })
      .then((response) => response.data),

  clearPreference: () =>
    api.delete("/api/v1/agent-storage/preference").then((response) => response.data),
};
