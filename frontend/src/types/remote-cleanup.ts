export type RemoteProtocol = "sftp" | "ftps" | "ftp";

/** Credenciales efímeras de conexión: contraseña O llave privada .pem (solo SFTP).
 *  Viven solo en memoria — nunca se persisten. */
export interface RemoteCreds {
  password?:   string;
  privateKey?: string;
  passphrase?: string;
}

export interface CleanupServer {
  id:        string;
  name:      string;
  transport?: "agent" | "remote";
  agentId?:  string | null;
  protocol:  RemoteProtocol | null;
  host:      string | null;
  port:      number | null;
  username:  string | null;
  rutaBase:  string;
  allowlist: string[];
  targetFolders?: string[];
  targetFiles?: string[];
  createdAt?: string;
}

export interface RemoteEntry {
  name:        string;
  path:        string;
  sizeBytes:   number;
  modified:    number | null;   // epoch (segundos)
  isDir:       boolean;
  isLink?:     boolean;
  permissions: string | null;
}

export interface RemoteListResponse {
  path:     string;
  entries:  RemoteEntry[];
  total:    number;
  page:     number;
  pageSize: number;
}

export interface ExcludedItem {
  path:   string;
  reason: string;
}

export interface SimulationReport {
  simulacion:           boolean;
  encontrados:          number;
  elegibles:            RemoteEntry[];
  elegiblesCount:       number;
  espacioLiberadoBytes: number;
  excluidos:            ExcludedItem[];
  excluidosCount:       number;
  protegidos:           ExcludedItem[];
  protegidosCount:      number;
  warnings:             string[];
  truncated?:           boolean;
  targets?:             string[];
}

export interface QuarantineItem {
  id:            string;
  execId:        string;
  serverId:      string;
  name:          string;
  originalPath:  string;
  quarantinePath: string;
  sizeBytes:     number;
  movedAt:       string;
  actor:         string;
  retentionDays: number;
}

export interface ExecutionRecord {
  id:           string;
  tipo:         string;
  serverId:     string;
  serverName:   string;
  targets:      string[];
  actor:        string;
  startedAt:    string;
  finishedAt:   string;
  encontrados:  number;
  elegibles:    number;
  movidos:      number;
  omitidos:     number;
  fallidos:     number;
  espacioBytes: number;
  estado:       string;
  cuarentena:   boolean;
}

/** Regla de limpieza ESTRUCTURAL (Ipsofactu: vaciar core/{...} y borrar archivos por
 *  nombre, replicado en cada propiedad bajo una raíz). */
export interface StructuralRule {
  tipo?:               "estructural";
  raiz?:               string;
  carpetaContenedora?: string;
  vaciarCarpetas:      string[];
  borrarArchivos:      string[];
  limites?:            { maxArchivosPorEjecucion?: number; maxBytesPorEjecucion?: number };
}

export interface StructuralReport {
  simulationId?:          string;
  manifestHash?:          string;
  simulacion?:           boolean;
  encontrados:           number;
  elegibles:             (RemoteEntry & { propiedad?: string })[];
  elegiblesCount:        number;
  espacioLiberadoBytes:  number;
  excluidos:             ExcludedItem[];
  excluidosCount:        number;
  protegidos:            ExcludedItem[];
  protegidosCount:       number;
  propiedadesAfectadas:  number;
  porPropiedad:          Record<string, number>;
  propiedadesTotales?:   number;
  propiedadesConCore?:   number;
  truncated?:            boolean;
  raiz?:                 string;
  warnings:              string[];
}

/** Estado de un job en segundo plano (limpieza estructural a escala). */
export interface CleanupJob {
  id:                    string;
  kind:                  "simulate" | "execute";
  status:                "running" | "completado" | "cancelado" | "error";
  fase:                  string;
  propiedadesTotales:    number;
  propiedadesProcesadas: number;
  encontrados:           number;
  result:                StructuralReport | (Record<string, any>) | null;
  error:                 string | null;
}

export interface AgentCleanupJob {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  phase: string;
  totalUnits: number;
  processedUnits: number;
  foundCount: number;
  result: Record<string, any> | null;
  error: string | null;
}

/** Regla mínima para la simulación (Fase 3). */
export interface SimRule {
  rutasPermitidas?:      string[];
  extensionesPermitidas?: string[];
  antiguedadMinimaDias?: number;
  noModificadoUltimasHoras?: number;
  exclusiones?:          string[];
  eliminarCarpetas?:     boolean;
  limites?:              { maxArchivosPorEjecucion?: number; maxBytesPorEjecucion?: number };
}
