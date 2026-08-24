export type FileBackupStrategy = "full" | "incremental" | "differential";
export type FileBackupRunStatus =
  | "queued"
  | "preflight"
  | "running"
  | "completed"
  | "completed_with_warnings"
  | "retryable"
  | "failed"
  | "cancelled";

export interface FileBackupTask {
  id: string;
  tenantId: string;
  name: string;
  agentId: string;
  destinationProfileId: string;
  sources: Array<{ path: string; includeSubfolders: boolean }>;
  filters: Array<{
    kind: "include" | "exclude";
    operator: "glob" | "extension" | "relative_path";
    pattern: string;
    isEnabled: boolean;
  }>;
  strategy: FileBackupStrategy;
  format: "direct" | "zip64";
  schedule: { weekdays: number[]; localTime: string };
  timezoneName: string;
  retentionFullChains: number;
  configRevision: number;
  isActive: boolean;
  firstRunWillBeFull: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface FileBackupRun {
  id: string;
  taskId: string;
  agentId: string;
  status: FileBackupRunStatus;
  strategy: FileBackupStrategy;
  phase: string;
  progressPercent: number;
  filesTotal: number | null;
  filesProcessed: number;
  bytesTotal: number | null;
  bytesProcessed: number;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface FileBackupPage<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}
