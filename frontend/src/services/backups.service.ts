import api from "@/lib/api";
import type { AgentBackupPlan, BackupRecord, BackupListResponse, DatabasesResponse } from "@/types/backup";
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
    const { data } = await api.post("/api/v1/backups/runs", payload);
    return data;
  },

  async listAgentPlans(): Promise<{ items: AgentBackupPlan[]; total: number }> {
    const { data } = await api.get("/api/v1/backups/plans");
    return data;
  },

  async createAgentPlan(payload: {
    agentId: string;
    sqlProfileId: string;
    destinationProfileId?: string;
    databaseNames: string[];
    fullDays: number[];
    differentialDays: number[];
    hourUtc: number;
  }): Promise<AgentBackupPlan> {
    const { data } = await api.post("/api/v1/backups/plans", payload);
    return data;
  },

  async deleteAgentPlan(planId: string): Promise<void> {
    await api.delete(`/api/v1/backups/plans/${planId}`);
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
