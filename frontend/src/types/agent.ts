export interface AgentConfiguration {
  id: string;
  name: string;
  transport: "agent";
  agentId: string;
  root: string;
  targetFolders: string[];
  targetFiles: string[];
  configRevision: number;
  configurationHash: string | null;
  validatedAt: string | null;
}

export interface AgentRecord {
  id: string;
  hostname: string;
  osVersion: string;
  agentVersion: string;
  status: string;
  online: boolean;
  lastSeenAt: string | null;
  revokedAt: string | null;
  createdAt: string | null;
  metadata: {
    sqlInstances?: AgentProfile[];
    backupDestinations?: AgentDestinationProfile[];
  };
  configuration: AgentConfiguration | null;
}

export interface AgentProfile {
  id: string;
  label: string;
}

export interface AgentDestinationProfile extends AgentProfile {
  type?: string;
}

export interface AgentProfiles {
  agentId: string;
  sqlInstances: AgentProfile[];
  backupDestinations: AgentDestinationProfile[];
}

export interface AgentJob<T = Record<string, unknown>> {
  id: string;
  kind: string;
  status: "queued" | "running" | "claimed" | "completed" | "failed" | "cancelled";
  phase: string;
  totalUnits: number;
  processedUnits: number;
  foundCount: number;
  result: T | null;
  error: string | null;
  cancelRequested: boolean;
}

export interface CleanupSimulationResult {
  simulationId: string;
  manifestHash: string;
  expiresAt: string;
  root: string;
  propertiesProcessed: number;
  propertiesAffected: number;
  eligibleCount: number;
  bytesEligible: number;
  samples: Array<{ relativePath: string; sizeBytes: number }>;
  truncated: boolean;
}

export interface CleanupExecutionResult {
  deletedCount: number;
  bytesDeleted: number;
  failedCount: number;
  errors: Array<{ relativePath: string; code: string }>;
  root: string;
}
