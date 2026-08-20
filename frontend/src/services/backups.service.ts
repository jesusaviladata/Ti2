import api from "@/lib/api";
import type { AgentBackupPlan, AgentJob, BackupAgent, BackupRecord, BackupListResponse, DatabasesResponse } from "@/types/backup";
import type { ConnectionPayload } from "@/types/connection";

export const backupsService = {
  async listBackups(skip = 0, limit = 50): Promise<BackupListResponse> {
    const { data } = await api.get("/api/v1/backups", { params: { skip, limit } });
    return data;
  },

  /** List databases using env-var connection (no active connection selected) */
  async listDatabases(): Promise<DatabasesResponse> {
    const { data } = await api.get("/api/v1/backups/databases");
    return data;
  },

  /** List databases for a specific SQL Server connection */
  async listDatabasesForConnection(conn: ConnectionPayload): Promise<DatabasesResponse> {
    const { data } = await api.post("/api/v1/connections/databases", conn);
    return data;
  },

  async listAgents(): Promise<{ items: BackupAgent[]; total: number }> {
    const { data } = await api.get("/api/v1/backups/agents");
    return data;
  },

  async startAgentDatabaseList(agentId: string, sqlProfileId: string): Promise<{ jobId: string }> {
    const { data } = await api.post("/api/v1/backups/agent-databases", {
      agent_id: agentId,
      sql_profile_id: sqlProfileId,
    });
    return data;
  },

  async getAgentJob(jobId: string): Promise<AgentJob> {
    const { data } = await api.get(`/api/v1/backups/agent-jobs/${jobId}`);
    return data;
  },

  async listAgentDatabases(agentId: string, sqlProfileId: string): Promise<DatabasesResponse> {
    const { jobId } = await this.startAgentDatabaseList(agentId, sqlProfileId);
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await this.getAgentJob(jobId);
      if (job.status === "completed") {
        return {
          databases: (job.result?.databases as string[]) ?? [],
          connected: true,
        };
      }
      if (job.status === "failed" || job.status === "cancelled") {
        return { databases: [], connected: false, error: job.error ?? "El agente no pudo consultar SQL Server" } as DatabasesResponse;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    return {
      databases: [],
      connected: false,
      error: "El agente no respondio dentro de 2 minutos",
    } as DatabasesResponse;
  },

  /** Test a connection — returns { connected, error?, databases? } */
  async testConnection(conn: ConnectionPayload): Promise<DatabasesResponse & { connected: boolean }> {
    const { data } = await api.post("/api/v1/connections/test", conn);
    return data;
  },

  async triggerBackup(payload: {
    database_names: string[];
    backup_type:    "full" | "differential" | "log";
    destination:    "local" | "nas" | "secondary_server";
    local_path?:    string;
    connection?:    ConnectionPayload;
  }): Promise<{ backups: BackupRecord[] }> {
    const { data } = await api.post("/api/v1/backups/manual", payload);
    return data;
  },

  async triggerAgentBackup(payload: {
    agentId: string;
    sqlProfileId: string;
    databaseNames: string[];
    backupType: "full" | "differential" | "log";
    destinationProfileId?: string;
  }): Promise<{ jobId: string; backups: BackupRecord[] }> {
    const { data } = await api.post("/api/v1/backups/manual-agent", {
      agent_id: payload.agentId,
      sql_profile_id: payload.sqlProfileId,
      database_names: payload.databaseNames,
      backup_type: payload.backupType,
      destination_profile_id: payload.destinationProfileId,
    });
    return data;
  },

  async listAgentPlans(): Promise<{ items: AgentBackupPlan[]; total: number }> {
    const { data } = await api.get("/api/v1/backups/agent-plans");
    return data;
  },

  async createAgentPlan(payload: {
    name: string;
    agentId: string;
    sqlProfileId: string;
    destinationProfileId?: string;
    databaseNames: string[];
    fullDays: number[];
    differentialDays: number[];
    localTime: string;
    timezone: string;
    enabled: boolean;
  }): Promise<AgentBackupPlan> {
    const { data } = await api.post("/api/v1/backups/agent-plans", payload);
    return data;
  },

  async updateAgentPlan(
    planId: string,
    payload: Partial<Pick<AgentBackupPlan, "name" | "databaseNames" | "fullDays" | "differentialDays" | "localTime" | "timezone" | "enabled" | "destinationProfileId">>,
  ): Promise<AgentBackupPlan> {
    const { data } = await api.put(`/api/v1/backups/agent-plans/${planId}`, payload);
    return data;
  },

  async deleteAgentPlan(planId: string): Promise<void> {
    await api.delete(`/api/v1/backups/agent-plans/${planId}`);
  },

  async retryDelivery(backupId: string): Promise<{ jobId: string }> {
    const { data } = await api.post(`/api/v1/backups/${backupId}/delivery/retry`);
    return data;
  },

  async getStatus(backupId: string): Promise<BackupRecord> {
    const { data } = await api.get(`/api/v1/backups/${backupId}/status`);
    return data;
  },

  async checkIntegrity(backupId: string) {
    const { data } = await api.get(`/api/v1/backups/integrity/${backupId}`);
    return data;
  },
};
