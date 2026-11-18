import api from "@/lib/api";
import type { AgentModuleStatus } from "@/types/agent";

export const agentModuleService = {
  status: () =>
    api.get<AgentModuleStatus>("/api/v1/agent-module").then((response) => response.data),

  setEnabled: (enabled: boolean) =>
    api.put<AgentModuleStatus>("/api/v1/agent-module", { enabled }).then((response) => response.data),

  /** Descarga el bootstrap.json de esta instalación: URL del panel y llave pública de firma. */
  downloadBootstrap: async () => {
    const response = await api.get<Blob>("/api/v1/agent-module/bootstrap", { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = "bootstrap.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
    } finally {
      URL.revokeObjectURL(url);
    }
  },
};
