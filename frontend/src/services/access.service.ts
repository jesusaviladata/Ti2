import api from "@/lib/api";
import type { AccessSession, CreateSessionPayload } from "@/types/access";

export const accessService = {
  createSession: (payload: CreateSessionPayload): Promise<AccessSession> =>
    api.post("/api/v1/access/sessions", payload).then((r) => r.data),

  listSessions: (status: "active" | "closed" = "active"): Promise<{ sessions: AccessSession[] }> =>
    api.get(`/api/v1/access/sessions?status=${status}`).then((r) => r.data),

  closeSession: (id: string, notes = ""): Promise<AccessSession> =>
    api.put(`/api/v1/access/sessions/${id}/close`, { notes }).then((r) => r.data),

  getLogs: (): Promise<{ logs: AccessSession[] }> =>
    api.get("/api/v1/access/logs").then((r) => r.data),

  getAlerts: (): Promise<{ alerts: AccessSession[] }> =>
    api.get("/api/v1/access/alerts").then((r) => r.data),

  downloadLog: (): Promise<Blob> =>
    api.get("/api/v1/access/download", { responseType: "blob" }).then((r) => r.data),

  deleteSession: (id: string): Promise<{ deleted: string }> =>
    api.delete(`/api/v1/access/sessions/${id}/delete`).then((r) => r.data),
};
