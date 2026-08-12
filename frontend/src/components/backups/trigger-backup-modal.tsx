"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { X, Database, Loader2, Search, ChevronDown, Check, Eye, EyeOff, CheckCircle2, XCircle, Clock, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgentDatabases, useBackupAgents, useDatabases, useTriggerAgentBackup, useTriggerBackup, useBackupStatus } from "@/hooks/useBackups";
import { useConnectionsStore } from "@/store/connections.store";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";

type BackupType  = "full" | "differential" | "log";
type Destination = "local" | "nas" | "secondary_server";
type ExecutionMode = "agent" | "direct";

interface DestinationCreds {
  host:     string;
  username: string;
  password: string;
  path:     string;
  domain:   string;
}

interface Props {
  open:    boolean;
  onClose: () => void;
}

const BACKUP_TYPES: { value: BackupType; label: string; desc: string }[] = [
  { value: "full",         label: "Completo",     desc: "Copia íntegra de la base de datos" },
  { value: "differential", label: "Diferencial",  desc: "Solo cambios desde el último Full" },
  { value: "log",          label: "Log de trans.", desc: "Registros de transacciones" },
];

const DESTINATIONS: { value: Destination; label: string }[] = [
  { value: "local",            label: "Disco local" },
  { value: "nas",              label: "NAS / Red" },
  { value: "secondary_server", label: "Servidor secundario" },
];

// ── Database multi-select searchable dropdown ─────────────────────────────────
function DbMultiSearchDropdown({
  databases,
  selected,
  onChange,
}: {
  databases: string[];
  selected:  string[];
  onChange:  (v: string[]) => void;
}) {
  const [open,   setOpen]   = useState(false);
  const [search, setSearch] = useState("");
  const ref      = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = databases.filter((db) =>
    db.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
    else setSearch("");
  }, [open]);

  function toggle(db: string) {
    onChange(selected.includes(db) ? selected.filter((x) => x !== db) : [...selected, db]);
  }

  function toggleAll() {
    onChange(selected.length === databases.length ? [] : [...databases]);
  }

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "w-full min-h-11 bg-musgo/10 border rounded-[0.75rem] px-4 py-2.5 text-sm text-left flex items-center justify-between gap-2 transition-colors",
          open ? "border-arcilla/50" : "border-musgo/30 hover:border-musgo/50",
        )}
      >
        <span className={cn("flex-1 font-mono text-xs", selected.length ? "text-crema" : "text-crema/35")}>
          {selected.length === 0
            ? "Selecciona una o más bases de datos…"
            : selected.length === 1
            ? selected[0]
            : `${selected.length} bases de datos seleccionadas`}
        </span>
        <ChevronDown size={14} className={cn("text-crema/30 shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {/* Selected chips */}
      {selected.length > 1 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {selected.map((db) => (
            <span key={db} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-arcilla/10 border border-arcilla/25 font-mono text-[10px] text-arcilla/80">
              {db}
              <button type="button" onClick={() => toggle(db)} className="text-arcilla/40 hover:text-arcilla ml-0.5">×</button>
            </span>
          ))}
        </div>
      )}

      {/* Dropdown panel */}
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 rounded-[0.875rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
          {/* Search */}
          <div className="flex items-center gap-2 px-3 py-2.5 border-b border-musgo/20">
            <Search size={13} className="text-crema/30 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar base de datos…"
              className="flex-1 bg-transparent text-xs font-mono text-crema/70 placeholder-crema/25 outline-none"
            />
            {search && (
              <button type="button" onClick={() => setSearch("")} className="text-crema/25 hover:text-crema/50 text-xs">✕</button>
            )}
          </div>

          {/* Select all */}
          {!search && (
            <button
              type="button"
              onClick={toggleAll}
              className="w-full text-left px-4 py-2 font-mono text-[10px] text-crema/40 hover:text-crema/60 hover:bg-musgo/10 transition-colors border-b border-musgo/10 flex items-center gap-2"
            >
              <div className={cn(
                "w-3.5 h-3.5 rounded-sm border flex items-center justify-center shrink-0",
                selected.length === databases.length
                  ? "bg-arcilla border-arcilla"
                  : "border-musgo/40"
              )}>
                {selected.length === databases.length && <Check size={9} className="text-white" />}
              </div>
              Seleccionar todas ({databases.length})
            </button>
          )}

          {/* List */}
          <div className="max-h-48 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <p className="font-mono text-xs text-crema/25 px-4 py-3">Sin resultados para "{search}"</p>
            ) : (
              filtered.map((db) => {
                const isSelected = selected.includes(db);
                return (
                  <button
                    key={db}
                    type="button"
                    onClick={() => toggle(db)}
                    className={cn(
                      "w-full text-left px-4 py-2 font-mono text-xs flex items-center gap-3 transition-colors",
                      isSelected ? "bg-arcilla/8 text-crema" : "text-crema/60 hover:bg-musgo/10 hover:text-crema/80"
                    )}
                  >
                    <div className={cn(
                      "w-3.5 h-3.5 rounded-sm border flex items-center justify-center shrink-0",
                      isSelected ? "bg-arcilla border-arcilla" : "border-musgo/40"
                    )}>
                      {isSelected && <Check size={9} className="text-white" />}
                    </div>
                    <span className="truncate">{db}</span>
                  </button>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-musgo/15 px-3 py-1.5 flex items-center justify-between">
            <span className="font-mono text-[10px] text-crema/20">
              {filtered.length} de {databases.length} bases de datos
            </span>
            {selected.length > 0 && (
              <span className="font-mono text-[10px] text-arcilla/60">
                {selected.length} seleccionada{selected.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Destination credential fields ─────────────────────────────────────────────
const INPUT = [
  "w-full h-9 rounded-[0.625rem]",
  "bg-carbon border border-musgo/30",
  "px-3 font-mono text-xs text-crema/75",
  "placeholder:text-crema/20",
  "focus:outline-none focus:border-arcilla/50",
  "transition-colors duration-150",
].join(" ");

function CredField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <p className="font-mono text-[10px] text-crema/35 uppercase tracking-wider">{label}</p>
      {children}
    </div>
  );
}

function DestinationCredentials({
  destination,
  creds,
  onChange,
}: {
  destination: Destination;
  creds:       DestinationCreds;
  onChange:    (patch: Partial<DestinationCreds>) => void;
}) {
  const [showPw, setShowPw] = useState(false);

  if (destination === "local") return null;

  const isNas = destination === "nas";

  return (
    <div className="rounded-[1rem] border border-musgo/25 overflow-hidden">
      {/* Section header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-musgo/15 border-b border-musgo/20">
        <span className="w-1.5 h-1.5 rounded-full bg-arcilla/60 shrink-0" />
        <p className="font-mono text-[10px] text-crema/40 uppercase tracking-widest">
          {isNas ? "Credenciales NAS / Red" : "Credenciales Servidor Secundario"}
        </p>
      </div>

      <div className="p-4 space-y-3 bg-musgo/5">
        {/* Row 1: host + path */}
        <div className="grid grid-cols-2 gap-3">
          <CredField label={isNas ? "Dirección / Host" : "Servidor (IP o hostname)"}>
            <input
              type="text"
              value={creds.host}
              onChange={(e) => onChange({ host: e.target.value })}
              placeholder={isNas ? "192.168.1.50" : "192.168.1.10"}
              className={INPUT}
            />
          </CredField>
          <CredField label={isNas ? "Ruta compartida" : "Ruta de destino"}>
            <input
              type="text"
              value={creds.path}
              onChange={(e) => onChange({ path: e.target.value })}
              placeholder={isNas ? "\\Backups\\SQL" : "C:\\Backups\\Remote"}
              className={INPUT}
            />
          </CredField>
        </div>

        {/* Row 2: domain (NAS only) + user + password */}
        <div className={cn("grid gap-3", isNas ? "grid-cols-3" : "grid-cols-2")}>
          {isNas && (
            <CredField label="Dominio (opcional)">
              <input
                type="text"
                value={creds.domain}
                onChange={(e) => onChange({ domain: e.target.value })}
                placeholder="WORKGROUP"
                className={INPUT}
              />
            </CredField>
          )}
          <CredField label="Usuario">
            <input
              type="text"
              value={creds.username}
              onChange={(e) => onChange({ username: e.target.value })}
              placeholder={isNas ? "usuario_red" : "admin"}
              className={INPUT}
            />
          </CredField>
          <CredField label="Contraseña">
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                value={creds.password}
                onChange={(e) => onChange({ password: e.target.value })}
                className={cn(INPUT, "pr-9")}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-crema/25 hover:text-crema/55 transition-colors"
              >
                {showPw ? <EyeOff size={12} /> : <Eye size={12} />}
              </button>
            </div>
          </CredField>
        </div>
      </div>
    </div>
  );
}

// ── Multi-backup progress list ────────────────────────────────────────────────
function BackupProgressRow({ backupId }: { backupId: string }) {
  const { data: backup } = useBackupStatus(backupId);

  const status = backup?.status ?? "pending";

  const barColor = {
    pending:   "bg-musgo/40",
    running:   "bg-arcilla",
    completed: "bg-green-500",
    failed:    "bg-red-500",
  }[status];

  const isRunning   = status === "running";
  const isCompleted = status === "completed";
  const isFailed    = status === "failed";

  return (
    <div className="rounded-[0.875rem] border border-musgo/20 bg-musgo/5 p-3.5 space-y-2.5">
      {/* Name + status icon */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-crema/80 truncate">{backup?.databaseName ?? "…"}</span>
        <span className="shrink-0">
          {isCompleted && <CheckCircle2 size={14} className="text-green-400" />}
          {isFailed    && <XCircle      size={14} className="text-red-400"   />}
          {!isCompleted && !isFailed && <Clock size={14} className="text-crema/25" />}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-musgo/20 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            barColor,
            isRunning && "animate-pulse w-3/4",
            isCompleted && "w-full",
            isFailed && "w-full",
            status === "pending" && "w-0",
          )}
        />
      </div>

      {/* Meta row */}
      <div className="flex items-center justify-between">
        <span className={cn("font-mono text-[10px]", {
          "text-crema/30":  status === "pending",
          "text-arcilla/70": status === "running",
          "text-green-400/70": isCompleted,
          "text-red-400/70": isFailed,
        })}>
          {status === "pending"   && "En cola…"}
          {status === "running"   && "Ejecutando…"}
          {isCompleted            && "Completado"}
          {isFailed               && "Fallido"}
        </span>
        {isCompleted && backup?.fileSizeBytes ? (
          <span className="font-mono text-[10px] text-crema/40">
            {formatBytes(backup.fileSizeBytes)}
          </span>
        ) : isFailed && backup?.errorMessage ? (
          <span className="font-mono text-[10px] text-red-400/60 truncate max-w-[60%] text-right">
            {backup.errorMessage.split("]").pop()?.trim().slice(0, 60)}
          </span>
        ) : null}
      </div>

      {/* File path when done */}
      {isCompleted && backup?.filePath && (
        <p className="font-mono text-[10px] text-green-400/50 break-all leading-relaxed border-t border-musgo/15 pt-2">
          {backup.filePath}
        </p>
      )}
    </div>
  );
}

function MultiBackupProgress({ backupIds }: { backupIds: string[] }) {
  return (
    <div className="space-y-2">
      <p className="font-mono text-[10px] text-crema/30 uppercase tracking-wider mb-3">
        {backupIds.length} tarea{backupIds.length !== 1 ? "s" : ""} en progreso
      </p>
      {backupIds.map((id) => (
        <BackupProgressRow key={id} backupId={id} />
      ))}
    </div>
  );
}

function todayLocalPath(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm   = String(d.getMonth() + 1).padStart(2, "0");
  const dd   = String(d.getDate()).padStart(2, "0");
  return `D:\\${yyyy}-${mm}-${dd}\\`;
}

// ── Main modal ─────────────────────────────────────────────────────────────────
export function TriggerBackupModal({ open, onClose }: Props) {
  const { getActive, toPayload } = useConnectionsStore();
  const activeConn  = getActive();
  const connPayload = activeConn ? toPayload(activeConn) : null;

  const [executionMode, setExecutionMode] = useState<ExecutionMode>("agent");
  const [agentId, setAgentId] = useState("");
  const [sqlProfileId, setSqlProfileId] = useState("");
  const [destinationProfileId, setDestinationProfileId] = useState("");
  const { data: agentData, isLoading: loadingAgents, isError: agentsUnavailable } = useBackupAgents(open);
  const selectedAgent = agentData?.items.find((item) => item.id === agentId);

  useEffect(() => {
    if (!agentId && agentData?.items.length) setAgentId(agentData.items[0].id);
  }, [agentData, agentId]);

  useEffect(() => {
    const profiles = selectedAgent?.sqlInstances ?? [];
    if (!profiles.some((item) => item.id === sqlProfileId)) {
      setSqlProfileId(profiles[0]?.id ?? "");
    }
    setDestinationProfileId("");
    setSelectedDbs([]);
  }, [selectedAgent, sqlProfileId]);

  const directDatabases = useDatabases(
    connPayload,
    activeConn?.id,
    open && executionMode === "direct",
  );
  const agentDatabases = useAgentDatabases(
    agentId,
    sqlProfileId,
    open && executionMode === "agent",
  );
  const dbData = executionMode === "agent" ? agentDatabases.data : directDatabases.data;
  const loadingDbs = executionMode === "agent" ? agentDatabases.isLoading : directDatabases.isLoading;
  const trigger = useTriggerBackup();
  const triggerAgent = useTriggerAgentBackup();

  const [selectedDbs,     setSelectedDbs]     = useState<string[]>([]);
  const [backupType,      setBackupType]      = useState<BackupType>("full");
  const [destination,     setDestination]     = useState<Destination>("local");
  const [localPath,       setLocalPath]       = useState<string>(todayLocalPath);
  const [destCreds,       setDestCreds]       = useState<DestinationCreds>({
    host: "", username: "", password: "", path: "", domain: "",
  });
  const [activeBackupIds, setActiveBackupIds] = useState<string[]>([]);

  if (!open) return null;

  function patchCreds(patch: Partial<DestinationCreds>) {
    setDestCreds((prev) => ({ ...prev, ...patch }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDbs.length) return;
    const result = executionMode === "agent"
      ? await triggerAgent.mutateAsync({
          agent_id: agentId,
          sql_profile_id: sqlProfileId,
          database_names: selectedDbs,
          backup_type: backupType,
          destination_profile_id: destinationProfileId || undefined,
        })
      : await trigger.mutateAsync({
          database_names: selectedDbs,
          backup_type:    backupType,
          destination,
          local_path:     destination === "local" ? localPath.trim() || undefined : undefined,
          connection:     connPayload ?? undefined,
        });
    setActiveBackupIds(result.backups.map((b) => b.id));
  }

  function handleClose() {
    setActiveBackupIds([]);
    setLocalPath(todayLocalPath());
    trigger.reset();
    triggerAgent.reset();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={handleClose} />

      <div className="relative z-10 w-full max-w-lg rounded-[1.5rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-musgo/20 shrink-0">
          <div>
            <p className="font-mono text-xs text-arcilla uppercase tracking-widest mb-0.5">Módulo Backups</p>
            <h2 className="font-display text-2xl italic font-light text-crema">
              Nuevo Backup<span className="text-arcilla">.</span>
            </h2>
            {activeConn && (
              <p className="font-mono text-[10px] text-crema/30 mt-0.5">→ {activeConn.label}</p>
            )}
          </div>
          <button onClick={handleClose} className="text-crema/30 hover:text-crema transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="p-6 overflow-y-auto">
          {!activeBackupIds.length ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="font-mono text-xs text-crema/40 uppercase tracking-wider block mb-2">
                  Ejecucion
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => { setExecutionMode("agent"); setSelectedDbs([]); }}
                    className={cn(
                      "h-10 rounded-[0.75rem] border text-xs font-sans transition-colors",
                      executionMode === "agent" ? "bg-arcilla/10 border-arcilla/40 text-crema" : "bg-musgo/10 border-musgo/20 text-crema/40",
                    )}
                  >
                    Agente del servidor
                  </button>
                  <button
                    type="button"
                    onClick={() => { setExecutionMode("direct"); setSelectedDbs([]); }}
                    className={cn(
                      "h-10 rounded-[0.75rem] border text-xs font-sans transition-colors",
                      executionMode === "direct" ? "bg-arcilla/10 border-arcilla/40 text-crema" : "bg-musgo/10 border-musgo/20 text-crema/40",
                    )}
                  >
                    Conexion directa
                  </button>
                </div>
              </div>

              {executionMode === "agent" && (
                <div className="rounded-[1rem] border border-musgo/25 bg-musgo/5 p-4 space-y-3">
                  <div>
                    <label className="font-mono text-[10px] text-crema/35 uppercase tracking-wider block mb-1.5">
                      Servidor / Agente
                    </label>
                    <select value={agentId} onChange={(event) => setAgentId(event.target.value)} className={INPUT}>
                      <option value="">Seleccione un servidor</option>
                      {agentData?.items.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.hostname} — {agent.status}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="font-mono text-[10px] text-crema/35 uppercase tracking-wider block mb-1.5">
                      Instancia SQL
                    </label>
                    <select value={sqlProfileId} onChange={(event) => setSqlProfileId(event.target.value)} className={INPUT}>
                      <option value="">Seleccione una instancia</option>
                      {selectedAgent?.sqlInstances.map((profile) => (
                        <option key={profile.id} value={profile.id}>{profile.label}</option>
                      ))}
                    </select>
                  </div>
                  {loadingAgents && <p className="font-mono text-[10px] text-crema/30">Consultando agentes…</p>}
                  {agentsUnavailable && (
                    <p className="font-mono text-[10px] text-red-400/70">
                      El modulo de agentes no esta disponible en Railway. Active el modulo o use conexion directa.
                    </p>
                  )}
                </div>
              )}

              {executionMode === "direct" && !activeConn && (
                <div className="flex items-center gap-2 rounded-[0.75rem] bg-musgo/10 border border-musgo/20 px-4 py-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-crema/20 shrink-0" />
                  <span className="font-mono text-xs text-crema/35">
                    Usando conexión por defecto (variables de entorno)
                  </span>
                </div>
              )}

              {/* Database selector */}
              <div>
                <label className="font-mono text-xs text-crema/40 uppercase tracking-wider block mb-2">
                  Bases de datos
                </label>
                {loadingDbs ? (
                  <div className="h-11 rounded-[0.75rem] bg-musgo/10 border border-musgo/20 flex items-center px-4 gap-2">
                    <Loader2 size={14} className="animate-spin text-crema/30" />
                    <span className="font-mono text-xs text-crema/30">Conectando a SQL Server…</span>
                  </div>
                ) : !dbData?.connected ? (
                  <div className="rounded-[0.75rem] bg-red-900/10 border border-red-800/30 px-4 py-3 space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                      <span className="font-mono text-xs text-red-400 font-medium">
                        {activeConn ? "No se pudo conectar al servidor SQL" : "Sin conexión SQL Server configurada"}
                      </span>
                    </div>
                    <p className="font-mono text-[10px] text-red-400/50 pl-3.5">
                      {activeConn
                        ? "Verifica que el servidor esté encendido y accesible en la red."
                        : "Ve a Configuración → Conexiones para agregar un servidor."}
                    </p>
                    {activeConn && (dbData as any)?.error && (
                      <p className="font-mono text-[10px] text-red-400/70 pl-3.5 break-all">
                        Detalle: {(dbData as any).error}
                      </p>
                    )}
                  </div>
                ) : (
                  <DbMultiSearchDropdown
                    databases={dbData.databases}
                    selected={selectedDbs}
                    onChange={setSelectedDbs}
                  />
                )}
              </div>

              {/* Backup type */}
              <div>
                <label className="font-mono text-xs text-crema/40 uppercase tracking-wider block mb-2">
                  Tipo de backup
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {BACKUP_TYPES.map(({ value, label, desc }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setBackupType(value)}
                      className={cn(
                        "p-3 rounded-[0.75rem] border text-left transition-all duration-150",
                        backupType === value
                          ? "bg-arcilla/10 border-arcilla/40 text-crema"
                          : "bg-musgo/10 border-musgo/20 text-crema/50 hover:border-musgo/40"
                      )}
                    >
                      <p className="font-sans text-xs font-medium">{label}</p>
                      <p className="font-mono text-[10px] mt-0.5 leading-tight opacity-60">{desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Destination */}
              <div>
                <label className="font-mono text-xs text-crema/40 uppercase tracking-wider block mb-2">
                  Destino
                </label>
                {executionMode === "agent" && (
                  <div className="rounded-[1rem] border border-musgo/25 bg-musgo/5 p-4 space-y-2">
                    <select value={destinationProfileId} onChange={(event) => setDestinationProfileId(event.target.value)} className={INPUT}>
                      <option value="">Solo carpeta local + ZIP</option>
                      {selectedAgent?.backupDestinations.map((profile) => (
                        <option key={profile.id} value={profile.id}>{profile.label}</option>
                      ))}
                    </select>
                    <p className="font-mono text-[10px] text-crema/25 leading-relaxed">
                      El agente crea la carpeta fechada, verifica los .bak y genera el ZIP antes de transferirlo.
                    </p>
                  </div>
                )}
                {executionMode === "direct" && <div className="flex gap-2">
                  {DESTINATIONS.map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setDestination(value)}
                      className={cn(
                        "flex-1 h-9 rounded-[0.75rem] border text-xs font-sans transition-all duration-150",
                        destination === value
                          ? "bg-musgo/40 border-musgo/60 text-crema"
                          : "bg-musgo/10 border-musgo/20 text-crema/40 hover:border-musgo/40"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>}

                {/* Local path config */}
                {executionMode === "direct" && destination === "local" && (
                  <div className="mt-3 rounded-[1rem] border border-musgo/25 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-2.5 bg-musgo/15 border-b border-musgo/20">
                      <FolderOpen size={12} className="text-arcilla/60 shrink-0" />
                      <p className="font-mono text-[10px] text-crema/40 uppercase tracking-widest">
                        Ruta de destino local
                      </p>
                    </div>
                    <div className="p-4 bg-musgo/5 space-y-2">
                      <input
                        type="text"
                        value={localPath}
                        onChange={(e) => setLocalPath(e.target.value)}
                        placeholder={`D:\\${new Date().toISOString().slice(0, 10)}\\`}
                        className={INPUT}
                      />
                      <p className="font-mono text-[10px] text-crema/25 leading-relaxed">
                        El archivo .bak se guardará dentro de esta carpeta. Si no existe, se creará automáticamente.
                      </p>
                    </div>
                  </div>
                )}

                {/* Credential fields for NAS / secondary server */}
                {executionMode === "direct" && destination !== "local" && (
                  <div className="mt-3">
                    <DestinationCredentials
                      destination={destination}
                      creds={destCreds}
                      onChange={patchCreds}
                    />
                  </div>
                )}
              </div>

              {(trigger.isError || triggerAgent.isError) && (
                <p className="font-mono text-xs text-red-400 bg-red-900/10 border border-red-800/20 rounded-[0.75rem] px-4 py-3">
                  {((triggerAgent.error ?? trigger.error) as any)?.response?.data?.detail ?? "Error al iniciar backup"}
                </p>
              )}

              <div className="flex gap-3 pt-1">
                <Button variant="outline" type="button" onClick={handleClose} className="flex-1">
                  Cancelar
                </Button>
                <Button
                  type="submit"
                  className="flex-1"
                  disabled={!selectedDbs.length || trigger.isPending || triggerAgent.isPending || !dbData?.connected || (executionMode === "agent" && (!agentId || !sqlProfileId))}
                >
                  {(trigger.isPending || triggerAgent.isPending) ? (
                    <><Loader2 size={14} className="animate-spin mr-2" />Iniciando…</>
                  ) : (
                    <><Database size={14} className="mr-2" />
                      {selectedDbs.length > 1 ? `Iniciar ${selectedDbs.length} Backups` : "Iniciar Backup"}
                    </>
                  )}
                </Button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <MultiBackupProgress backupIds={activeBackupIds} />
              <Button onClick={handleClose} variant="outline" className="w-full">
                Cerrar — los backups continúan en segundo plano
              </Button>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
