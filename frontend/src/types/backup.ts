export type BackupType        = "full" | "differential" | "log";
export type BackupStatus      = "pending" | "running" | "completed" | "failed";
export type BackupDestination = "local" | "nas" | "secondary_server" | "private_cloud";

export interface BackupRecord {
  id:            string;
  tenantId?:     string;
  databaseName:  string;
  backupType:    BackupType;
  status:        BackupStatus;
  destination:   BackupDestination;
  filePath?:     string | null;
  fileSizeBytes?: number | null;
  sha256Hash?:   string | null;
  errorMessage?: string | null;
  agentId?: string | null;
  runId?: string | null;
  phase?: string | null;
  progressPercent?: number;
  validationMethod?: string | null;
  triggerReason?: string | null;
  deliveryStatus?: "pending" | "processing" | "delivered" | "failed" | string;
  deliveryPhase?: string | null;
  deliveryProgress?: number;
  deliveryErrorMessage?: string | null;
  deliveryProfileId?: string | null;
  archivePath?: string | null;
  archiveSizeBytes?: number | null;
  archiveSha256?: string | null;
  startedAt?:    string | null;
  finishedAt?:   string | null;
  durationSecs?: number | null;
  createdAt:     string;
}

export interface BackupListResponse {
  items: BackupRecord[];
  total: number;
  skip:  number;
  limit: number;
}

export interface DatabasesResponse {
  databases: string[];
  connected: boolean;
  error?:    string;
}

export interface AgentBackupPlan {
  id: string;
  agentId: string;
  sqlProfileId: string;
  destinationProfileId: string | null;
  databaseNames: string[];
  fullDays: number[];
  differentialDays: number[];
  hourUtc: number;
  enabled: boolean;
  lastRunAt: string | null;
  createdAt: string;
}
