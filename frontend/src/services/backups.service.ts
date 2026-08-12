import api from "@/lib/api";
import type { AgentJob, BackupAgent, BackupRecord, BackupListResponse, DatabasesResponse } from "@/types/backup";
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
    agent_id: string;
    sql_profile_id: string;
    database_names: string[];
    backup_type: "full" | "differential" | "log";
    destination_profile_id?: string;
  }): Promise<{ jobId: string; backups: BackupRecord[] }> {
    const { data } = await api.post("/api/v1/backups/manual-agent", payload);
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
