export type UserRole = "admin" | "technician" | "supervisor" | "client";

export interface User {
  id: string;
  tenantId: string;
  email: string;
  username: string;
  fullName: string;
  role: UserRole;
  isActive: boolean;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface BackupStatus {
  id: string;
  databaseName: string;
  type: "full" | "differential" | "incremental";
  status: "pending" | "running" | "completed" | "failed";
  destination: "local" | "nas" | "secondary_server" | "private_cloud";
  fileSizeBytes?: number;
  startedAt?: string;
  finishedAt?: string;
  errorMessage?: string;
}

export interface AccessSession {
  id: string;
  userId: string;
  serverName: string;
  ipAddress: string;
  tool: string;
  reason?: string;
  startedAt: string;
  endedAt?: string;
  durationMinutes?: number;
  isSuspicious: boolean;
}
