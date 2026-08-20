import api from "@/lib/api";

export const agentCleanupService = {
  async simulate(agentId: string): Promise<{ jobId: string }> {
    const { data } = await api.post("/api/v1/cleanup/agent/simulations", { agentId });
    return data;
  },

  async execute(simulationJobId: string): Promise<{ jobId: string }> {
    const { data } = await api.post("/api/v1/cleanup/agent/executions", { simulationJobId });
    return data;
  },
};
