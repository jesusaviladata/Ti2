export type StorageState = "healthy" | "warning" | "critical" | "unknown";

export interface AgentVolumeState {
  agentId: string;
  agentName: string;
  volumeKey: string;
  label: string;
  mountPoint: string;
  totalBytes: number | null;
  freeBytes: number | null;
  freePercent: number | null;
  usedPercent: number | null;
  roles: Array<"backup" | "cleanup" | "destination">;
  observedAt: string;
  error: string | null;
  state: StorageState;
}

export interface StorageThresholds {
  warningFreePercent: number;
  warningFreeBytes: number;
  criticalFreePercent: number;
  criticalFreeBytes: number;
}

export interface StoragePreference {
  mode: "automatic" | "configured";
  agentId: string | null;
  volumeKey: string | null;
  available: boolean;
}

export interface AgentStorageInventory {
  items: AgentVolumeState[];
  total: number;
  summary: AgentVolumeState | null;
  featured: AgentVolumeState | null;
  preference: StoragePreference;
  thresholds: StorageThresholds;
}

export interface AgentStorageAlert {
  id: string;
  agentId: string;
  agentName: string;
  volumeKey: string;
  severity: "warning" | "critical";
  status: "open" | "resolved";
  freeBytes: number | null;
  totalBytes: number | null;
  freePercent: number | null;
  openedAt: string;
  lastObservedAt: string;
  resolvedAt: string | null;
}
