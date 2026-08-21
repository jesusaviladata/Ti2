export type ManagedProfileType = "sql" | "destination";
export type ProfileSyncStatus = "pending" | "applied" | "error" | "requires_secret";

export interface ManagedAgentProfile {
  id: string;
  agentId: string;
  profileType: ManagedProfileType;
  profileKey: string;
  label: string;
  publicConfig: Record<string, string | number | boolean>;
  desiredRevision: number;
  appliedRevision: number;
  syncStatus: ProfileSyncStatus;
  lastTestStatus?: "testing" | "ok" | "error" | null;
  lastTestAt?: string | null;
  lastError?: string | null;
  hasSecret: boolean;
  requiresSecret: boolean;
  isActive: boolean;
}

export interface ManagedProfileInput {
  profileType: ManagedProfileType;
  profileKey?: string;
  label: string;
  publicConfig: Record<string, string | number | boolean>;
  secret?: Record<string, string>;
  requiresSecret?: boolean;
}
