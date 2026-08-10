import api from "@/lib/api";
import type {
  CleanupFolder, CleanupRule, ScanResult,
  TrashItem, CleanupHistoryEntry, CleanupSchedule,
} from "@/types/cleanup";

type List<T> = { items: T[]; total: number };

export const cleanupService = {
  // Folders
  listFolders: () =>
    api.get<List<CleanupFolder>>("/api/v1/cleanup/folders").then((r) => r.data),
  addFolder: (body: { path: string; label?: string }) =>
    api.post<CleanupFolder>("/api/v1/cleanup/folders", body).then((r) => r.data),
  deleteFolder: (id: string) =>
    api.delete(`/api/v1/cleanup/folders/${id}`),

  // Rules
  listRules: () =>
    api.get<List<CleanupRule>>("/api/v1/cleanup/rules").then((r) => r.data),
  createRule: (body: Partial<CleanupRule>) =>
    api.post<CleanupRule>("/api/v1/cleanup/rules", body).then((r) => r.data),
  updateRule: (id: string, body: Partial<CleanupRule>) =>
    api.put<CleanupRule>(`/api/v1/cleanup/rules/${id}`, body).then((r) => r.data),
  deleteRule: (id: string) =>
    api.delete(`/api/v1/cleanup/rules/${id}`),

  // Scan
  scan: (folderId?: string) =>
    api.get<ScanResult>("/api/v1/cleanup/scan", {
      params: folderId ? { folder_id: folderId } : {},
    }).then((r) => r.data),

  // Execute
  execute: (filePaths: string[], ruleId?: string) =>
    api.post<{ moved: number; errors: { path: string; error: string }[]; bytesFreed: number }>(
      "/api/v1/cleanup/execute",
      { file_paths: filePaths, rule_id: ruleId ?? null }
    ).then((r) => r.data),

  // Trash
  listTrash: () =>
    api.get<List<TrashItem>>("/api/v1/cleanup/trash").then((r) => r.data),
  permanentDelete: (id: string) =>
    api.delete(`/api/v1/cleanup/trash/${id}`),
  restore: (id: string) =>
    api.post(`/api/v1/cleanup/restore/${id}`).then((r) => r.data),

  // History
  listHistory: (skip = 0, limit = 50) =>
    api.get<List<CleanupHistoryEntry>>("/api/v1/cleanup/history", {
      params: { skip, limit },
    }).then((r) => r.data),

  // Schedules
  listSchedules: () =>
    api.get<List<CleanupSchedule>>("/api/v1/cleanup/schedules").then((r) => r.data),
  createSchedule: (body: Partial<CleanupSchedule>) =>
    api.post<CleanupSchedule>("/api/v1/cleanup/schedules", body).then((r) => r.data),
  updateSchedule: (id: string, body: Partial<CleanupSchedule>) =>
    api.put<CleanupSchedule>(`/api/v1/cleanup/schedules/${id}`, body).then((r) => r.data),
  deleteSchedule: (id: string) =>
    api.delete(`/api/v1/cleanup/schedules/${id}`),
};
