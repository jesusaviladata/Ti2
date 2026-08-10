import api from "@/lib/api";
import type { FMConnection, FMListResponse } from "@/types/filemanager";

type ConnPayload = Pick<FMConnection, "host" | "port" | "protocol" | "username" | "password" | "privateKey" | "passphrase"> | null;

export const fmService = {
  async test(conn: ConnPayload): Promise<{ connected: boolean; error?: string }> {
    const { data } = await api.post("/api/v1/fm/test", conn);
    return data;
  },

  async list(conn: ConnPayload, path: string): Promise<FMListResponse> {
    const { data } = await api.post("/api/v1/fm/list", { connection: conn, path });
    return data;
  },

  async delete(conn: ConnPayload, path: string, contentsOnly = false): Promise<{ deleted: number }> {
    const { data } = await api.post("/api/v1/fm/delete", {
      connection:    conn,
      path,
      contents_only: contentsOnly,
    });
    return data;
  },

  async mkdir(conn: ConnPayload, path: string): Promise<void> {
    await api.post("/api/v1/fm/mkdir", { connection: conn, path });
  },
};
