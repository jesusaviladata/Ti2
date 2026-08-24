import api from "@/lib/api";
import type {
  FileBackupPage,
  FileBackupRun,
  FileBackupStrategy,
  FileBackupTask,
} from "@/types/file-backup";

export const fileBackupsService = {
  async listTasks(page = 1, pageSize = 50): Promise<FileBackupPage<FileBackupTask>> {
    const { data } = await api.get("/api/v1/file-backup/tasks", {
      params: { page, pageSize },
    });
    return data;
  },

  async listRuns(taskId: string, page = 1, pageSize = 20): Promise<FileBackupPage<FileBackupRun>> {
    const { data } = await api.get(`/api/v1/file-backup/tasks/${taskId}/runs`, {
      params: { page, pageSize },
    });
    return data;
  },

  async startRun(taskId: string, strategy?: FileBackupStrategy): Promise<FileBackupRun> {
    const { data } = await api.post(`/api/v1/file-backup/tasks/${taskId}/runs`, {
      strategy,
    });
    return data;
  },

  async simulate(taskId: string): Promise<{ id: string; taskId: string; status: string }> {
    const { data } = await api.post(`/api/v1/file-backup/tasks/${taskId}/simulations`);
    return data;
  },
};
