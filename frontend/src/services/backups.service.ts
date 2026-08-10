import api from "@/lib/api";
import type { BackupRecord, BackupListResponse, DatabasesResponse } from "@/types/backup";
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

  async getStatus(backupId: string): Promise<BackupRecord> {
    const { data } = await api.get(`/api/v1/backups/${backupId}/status`);
    return data;
  },

  async checkIntegrity(backupId: string) {
    const { data } = await api.get(`/api/v1/backups/integrity/${backupId}`);
    return data;
  },
};
