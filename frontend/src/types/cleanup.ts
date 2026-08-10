export type KeepPolicy = "latest" | "latest_n" | "none" | "all";
export type CleanupStatus = "completed" | "partial" | "failed";

export interface CleanupFolder {
  id:        string;
  path:      string;
  label:     string;
  enabled:   boolean;
  exists:    boolean;
  createdAt: string;
}

export interface CleanupRule {
  id:         string;
  name:       string;
  folderId:   string | null;
  patterns:   string[];
  extensions: string[];
  keep:       KeepPolicy;
  keepN:      number;
  minAgeDays: number;
  enabled:    boolean;
  createdAt:  string;
}

export interface ScannedFile {
  id:           string;
  name:         string;
  path:         string;
  relativePath: string;
  sizeBytes:    number;
  modifiedAt:   string;
  ageDays:      number;
  ruleId:       string;
  ruleName:     string;
  folderId:     string;
}

export interface ScanResult {
  files:      ScannedFile[];
  total:      number;
  totalBytes: number;
  scannedAt:  string;
}

export interface TrashItem {
  id:           string;
  name:         string;
  originalPath: string;
  trashPath:    string;
  sizeBytes:    number;
  ruleId:       string | null;
  deletedAt:    string;
}

export interface CleanupHistoryEntry {
  id:           string;
  filesDeleted: number;
  bytesFreed:   number;
  errors:       number;
  executedAt:   string;
  status:       CleanupStatus;
}

export interface CleanupSchedule {
  id:        string;
  name:      string;
  folderId:  string;
  ruleId:    string;
  cronExpr:  string;
  enabled:   boolean;
  lastRun:   string | null;
  nextRun:   string | null;
  createdAt: string;
}
