import api from "@/lib/api";
import type {
  CleanupServer, RemoteListResponse, SimulationReport, SimRule,
  ExecutionRecord, QuarantineItem, RemoteCreds,
  StructuralRule, StructuralReport, CleanupJob,
  AgentCleanupJob,
} from "@/types/remote-cleanup";

export const remoteCleanupService = {
  listServers: () =>
    api.get<{ items: CleanupServer[]; total: number }>("/api/v1/cleanup/remote/servers").then((r) => r.data),

  createServer: (body: Omit<CleanupServer, "id" | "createdAt">) =>
    api.post<CleanupServer>("/api/v1/cleanup/remote/servers", body).then((r) => r.data),

  deleteServer: (id: string) =>
    api.delete(`/api/v1/cleanup/remote/servers/${id}`).then((r) => r.data),

  list: (server_id: string, creds: RemoteCreds, path?: string, page = 1, pageSize = 200) =>
    api
      .post<RemoteListResponse>("/api/v1/cleanup/remote/list", { server_id, ...creds, path, page, pageSize })
      .then((r) => r.data),

  simulate: (server_id: string, creds: RemoteCreds, rule: SimRule) =>
    api
      .post<SimulationReport>("/api/v1/cleanup/remote/simulate", { server_id, ...creds, rule })
      .then((r) => r.data),

  // Ejecuta la limpieza = MOVER a cuarentena (reversible). Exige confirmar + el conteo
  // que el usuario vio en la simulación (si cambió, el backend aborta con 409).
  execute: (server_id: string, creds: RemoteCreds, rule: SimRule, conteoEsperado: number) =>
    api
      .post("/api/v1/cleanup/remote/execute", { server_id, ...creds, rule, confirmar: true, conteoEsperado })
      .then((r) => r.data),

  // ── Limpieza estructural (Ipsofactu: N propiedades) — jobs en segundo plano ──
  // Devuelven un jobId; se consulta el progreso con structuralJob().
  structuralSimulate: (server_id: string, creds: RemoteCreds, rule: StructuralRule, maxPropiedades = 0) =>
    api
      .post<{ jobId: string }>("/api/v1/cleanup/remote/structural/simulate", { server_id, ...creds, rule, maxPropiedades })
      .then((r) => r.data),

  // modo: "cuarentena" (reversible) | "directo" (borra). Exige el conteo de la simulación.
  structuralExecute: (
    server_id: string, creds: RemoteCreds, rule: StructuralRule,
    modo: "cuarentena" | "directo", conteoEsperado: number, maxPropiedades = 0,
  ) =>
    api
      .post<{ jobId: string }>("/api/v1/cleanup/remote/structural/execute", {
        server_id, ...creds, rule, modo, confirmar: true, conteoEsperado, maxPropiedades,
      })
      .then((r) => r.data),

  structuralJob: (jobId: string) =>
    api.get<CleanupJob>(`/api/v1/cleanup/remote/structural/job/${jobId}`).then((r) => r.data),

  structuralJobCancel: (jobId: string) =>
    api.post(`/api/v1/cleanup/remote/structural/job/${jobId}/cancel`).then((r) => r.data),

  agentStructuralSimulate: (agentId: string, serverId: string, containerFolder: string, maxProperties = 0) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/cleanup/simulate`, {
      serverId, containerFolder, maxProperties,
    }).then((r) => r.data),

  agentStructuralExecute: (agentId: string, simulationId: string, manifestHash: string) =>
    api.post<{ jobId: string }>(`/api/v1/agents/${agentId}/cleanup/quarantine`, {
      simulationId, manifestHash,
    }).then((r) => r.data),

  agentJob: (jobId: string) =>
    api.get<AgentCleanupJob>(`/api/v1/agents/jobs/${jobId}`).then((r) => r.data),

  agentJobCancel: (jobId: string) =>
    api.post(`/api/v1/agents/jobs/${jobId}/cancel`).then((r) => r.data),

  history: () =>
    api.get<{ items: ExecutionRecord[]; total: number }>("/api/v1/cleanup/remote/history").then((r) => r.data),

  quarantine: () =>
    api.get<{ items: QuarantineItem[]; total: number }>("/api/v1/cleanup/remote/quarantine").then((r) => r.data),

  restore: (qid: string, server_id: string, creds: RemoteCreds) =>
    api.post(`/api/v1/cleanup/remote/quarantine/${qid}/restore`, { server_id, ...creds }).then((r) => r.data),

  // Claves de host SSH conocidas (H-5)
  listHostKeys: () =>
    api.get<{ items: { host: string; fingerprint: string }[]; total: number }>("/api/v1/ssh/hostkeys").then((r) => r.data),

  forgetHostKey: (host: string, port: number) =>
    api.post("/api/v1/ssh/hostkeys/forget", { host, port }).then((r) => r.data),
};
