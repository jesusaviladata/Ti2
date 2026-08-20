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
};
