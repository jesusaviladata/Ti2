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

export interface BackupAgentProfile {
  id: string;
  label: string;
  type?: string;
}

export interface BackupAgent {
  id: string;
  hostname: string;
  status: string;
  lastSeenAt: string | null;
  sqlInstances: BackupAgentProfile[];
  backupDestinations: BackupAgentProfile[];
}

export interface AgentJob {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  phase: string;
  totalUnits: number;
  processedUnits: number;
  foundCount: number;
  result?: Record<string, any> | null;
  error?: string | null;
}

export interface AgentBackupPlan {
  id: string;
  name: string;
  agentId: string;
  sqlProfileId: string;
  destinationProfileId?: string | null;
  databaseNames: string[];
  localTime: string;
  timezone: string;
  enabled: boolean;
  fullDays: number[];
  differentialDays: number[];
  lastRunAt?: string | null;
  nextRunAt?: string | null;
  createdAt: string;
}

export interface DatabasesResponse {
  databases: string[];
  connected: boolean;
  error?:    string;
}
