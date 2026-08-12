"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface BackgroundBackupBatch {
  jobId?: string;
  backupIds: string[];
  databaseNames: string[];
  startedAt: string;
}

interface BackupProgressState {
  activeBatch: BackgroundBackupBatch | null;
  showInBackground: (batch: BackgroundBackupBatch) => void;
  dismissBackground: () => void;
}

export const useBackupProgressStore = create<BackupProgressState>()(
  persist(
    (set) => ({
      activeBatch: null,
      showInBackground: (batch) => set({ activeBatch: batch }),
      dismissBackground: () => set({ activeBatch: null }),
    }),
    {
      name: "data-express-backup-progress",
    },
  ),
);
