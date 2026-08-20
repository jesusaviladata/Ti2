"use client";

import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, Loader2, Radar, X } from "lucide-react";
import { useAgentJob } from "@/hooks/useAgents";
import { useDiscoverAgentEnvironment, useSaveManagedProfile } from "@/hooks/useAgentProfilesAdmin";
import type { AgentRecord } from "@/types/agent";


const STEPS = ["Detectar", "SQL Server", "Permisos", "Raíz", "Destino", "Limpieza", "Activar"];
const INPUT = "h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-sm text-crema/75 outline-none focus:border-arcilla/45";

export function AgentConnectionWizard({ agent, onClose }: { agent: AgentRecord; onClose: () => void }) {
  const save = useSaveManagedProfile(agent.id);
  const discover = useDiscoverAgentEnvironment(agent.id);
  const [discoveryJobId, setDiscoveryJobId] = useState<string | null>(null);
  const discovery = useAgentJob<{
    hostname?: string;
    serviceAccount?: string;
    sqlCandidates?: Array<{ server?: string; label?: string }>;
    destinationCandidates?: Array<{ type?: string; path?: string; label?: string }>;
  }>(discoveryJobId);
  const [step, setStep] = useState(0);
  const [sqlLabel, setSqlLabel] = useState("SQL Producción");
  const [server, setServer] = useState("localhost");
  const [backupRoot, setBackupRoot] = useState("D:\\Backups");
  const [destinationEnabled, setDestinationEnabled] = useState(true);
  const [destinationLabel, setDestinationLabel] = useState("Destino central");
  const [destinationType, setDestinationType] = useState<"smb" | "sftp">("smb");
  const [destinationPath, setDestinationPath] = useState("\\\\servidor\\backups");
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function detect() {
    setError(null);
    try {
      const queued = await discover.mutateAsync();
      setDiscoveryJobId(queued.jobId);
    } catch {
      setError("No se pudo iniciar la detección del agente");
    }
  }

  function useDiscovery() {
    const result = discovery.data?.result;
    const sql = result?.sqlCandidates?.[0];
    const destination = result?.destinationCandidates?.[0];
    if (sql?.server) setServer(sql.server);
    if (sql?.label) setSqlLabel(sql.label);
    if (destination?.path) setDestinationPath(destination.path);
    if (destination?.label) setDestinationLabel(destination.label);
    if (destination?.type === "smb" || destination?.type === "sftp") setDestinationType(destination.type);
    setStep(1);
  }

  async function activate() {
    setError(null);
    try {
      await save.mutateAsync({
        input: {
          profileType: "sql",
          profileKey: "sql-main",
          label: sqlLabel,
          publicConfig: { server, driver: "ODBC Driver 18 for SQL Server", authentication: "windows", backupRoot },
        },
      });
      if (destinationEnabled) {
        await save.mutateAsync({
          input: {
            profileType: "destination",
            profileKey: "destination-main",
            label: destinationLabel,
            publicConfig: destinationType === "smb"
              ? { type: "smb", path: destinationPath }
              : { type: "sftp", path: destinationPath, host, port: 22, username },
            secret: destinationType === "sftp" && privateKey ? { privateKey } : undefined,
          },
        });
      }
      onClose();
    } catch (value) {
      const response = value as { response?: { data?: { error?: { message?: string }; detail?: string } } };
      setError(response.response?.data?.error?.message ?? response.response?.data?.detail ?? "No se pudo guardar la configuración");
    }
  }

  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-black/70 p-4 backdrop-blur-sm">
      <section className="w-full max-w-3xl overflow-hidden rounded-[1.25rem] border border-musgo/30 bg-carbon">
        <header className="flex items-start justify-between border-b border-musgo/20 px-6 py-5">
          <div><p className="text-[10px] uppercase tracking-[0.18em] text-arcilla">Asistente de conexión · {agent.hostname}</p><h2 className="mt-1 text-xl font-medium text-crema">Conectar SQL Server y destino</h2></div>
          <button type="button" onClick={onClose} className="text-crema/35 hover:text-crema"><X size={17} /></button>
        </header>
        <div className="overflow-x-auto border-b border-musgo/15 px-6 py-3"><div className="flex min-w-max items-center gap-1">{STEPS.map((label, index) => <div key={label} className="flex items-center"><button type="button" onClick={() => setStep(index)} className={index === step ? "rounded-full bg-arcilla/15 px-3 py-1.5 text-[10px] text-arcilla" : index < step ? "rounded-full px-3 py-1.5 text-[10px] text-green-400" : "rounded-full px-3 py-1.5 text-[10px] text-crema/25"}>{index < step ? "✓ " : ""}{label}</button>{index < STEPS.length - 1 ? <span className="h-px w-4 bg-musgo/25" /> : null}</div>)}</div></div>
        <div className="min-h-64 space-y-4 p-6">
          {step === 0 ? <div className="space-y-4"><div className="rounded-[0.875rem] border border-green-500/20 bg-green-500/[0.05] p-4"><p className="text-sm text-green-300">Agente disponible para configuración</p><p className="mt-1 text-xs text-crema/40">{agent.hostname} · v{agent.agentVersion} · conexión cifrada por agente</p></div>{!discoveryJobId ? <button type="button" onClick={detect} disabled={discover.isPending} className="flex h-10 items-center gap-2 rounded-[0.625rem] border border-arcilla/30 bg-arcilla/10 px-4 text-xs text-arcilla disabled:opacity-40">{discover.isPending ? <Loader2 size={13} className="animate-spin" /> : <Radar size={13} />} Detectar configuración del servidor</button> : discovery.data?.status === "completed" ? <div className="rounded-[0.875rem] border border-musgo/25 p-4 text-xs text-crema/50"><p>Cuenta del servicio: <span className="text-crema/75">{discovery.data.result?.serviceAccount ?? "No disponible"}</span></p><p className="mt-1">SQL detectados: {discovery.data.result?.sqlCandidates?.length ?? 0} · destinos: {discovery.data.result?.destinationCandidates?.length ?? 0}</p><button type="button" onClick={useDiscovery} className="mt-3 text-arcilla">Usar datos detectados →</button></div> : discovery.data?.status === "failed" ? <p className="text-xs text-red-400">{discovery.data.error ?? "La detección falló"}</p> : <p className="flex items-center gap-2 text-xs text-crema/40"><Loader2 size={13} className="animate-spin text-arcilla" /> Esperando la respuesta del agente…</p>}{error ? <p className="text-xs text-red-400">{error}</p> : null}</div> : null}
          {step === 1 ? <div className="grid gap-4 sm:grid-cols-2"><label className="space-y-2 text-xs text-crema/45">Nombre visible<input className={INPUT} value={sqlLabel} onChange={(event) => setSqlLabel(event.target.value)} /></label><label className="space-y-2 text-xs text-crema/45">Servidor / instancia<input className={INPUT} value={server} onChange={(event) => setServer(event.target.value)} placeholder="localhost\\SQLEXPRESS" /></label></div> : null}
          {step === 2 ? <div className="space-y-3"><p className="text-sm text-crema/70">Autenticación integrada de Windows</p><p className="text-xs leading-relaxed text-crema/40">SQL Server reconocerá la cuenta real del servicio DataExpressAgent. Consulte StartName y reemplace CUENTA_SERVICIO en el script. No se guarda contraseña SQL.</p><button type="button" onClick={() => navigator.clipboard.writeText("# PowerShell: (Get-CimInstance Win32_Service -Filter \"Name='DataExpressAgent'\").StartName\n\n-- SQL Server: reemplace CUENTA_SERVICIO por el resultado anterior\nGRANT BACKUP DATABASE TO [CUENTA_SERVICIO];\nGRANT VIEW SERVER STATE TO [CUENTA_SERVICIO];")} className="rounded-[0.5rem] border border-musgo/25 px-3 py-2 text-xs text-arcilla">Copiar comprobación y permisos</button></div> : null}
          {step === 3 ? <label className="block space-y-2 text-xs text-crema/45">Raíz local de backups<input className={INPUT} value={backupRoot} onChange={(event) => setBackupRoot(event.target.value)} /><span className="block text-[10px] text-crema/30">Se crearán Fecha / FULL o DIFERENCIAL automáticamente.</span></label> : null}
          {step === 4 ? <div className="space-y-4"><label className="flex items-center gap-2 text-sm text-crema/65"><input type="checkbox" checked={destinationEnabled} onChange={(event) => setDestinationEnabled(event.target.checked)} /> Enviar ZIP a otro servidor</label>{destinationEnabled ? <><div className="grid grid-cols-2 gap-2">{(["smb","sftp"] as const).map((value) => <button type="button" key={value} onClick={() => setDestinationType(value)} className={destinationType === value ? "h-9 rounded-[0.5rem] border border-arcilla/35 bg-arcilla/10 text-xs text-arcilla" : "h-9 rounded-[0.5rem] border border-musgo/25 text-xs text-crema/40"}>{value.toUpperCase()}</button>)}</div><div className="grid gap-3 sm:grid-cols-2"><input className={INPUT} value={destinationLabel} onChange={(event) => setDestinationLabel(event.target.value)} placeholder="Nombre del destino" /><input className={INPUT} value={destinationPath} onChange={(event) => setDestinationPath(event.target.value)} placeholder={destinationType === "smb" ? "\\\\servidor\\backups" : "/backups"} />{destinationType === "sftp" ? <><input className={INPUT} value={host} onChange={(event) => setHost(event.target.value)} placeholder="Host" /><input className={INPUT} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Usuario" /><textarea className="min-h-24 rounded-[0.625rem] border border-musgo/25 bg-musgo/10 p-3 text-xs text-crema/65 outline-none sm:col-span-2" value={privateKey} onChange={(event) => setPrivateKey(event.target.value)} placeholder="Llave privada (se cifra para este agente)" /></> : null}</div></> : <p className="text-xs text-crema/35">Se aceptará sólo Full/ZIP local; no es obligatorio configurar diferenciales ni destino remoto.</p>}</div> : null}
          {step === 5 ? <div className="rounded-[0.875rem] border border-musgo/20 p-4"><p className="text-sm text-crema/70">Limpieza segura por propiedad</p><p className="mt-1 text-xs leading-relaxed text-crema/40">La raíz fija se configura aparte. El agente vacía únicamente archivos dentro de Propiedad\core\Log, LogSec, LogsRadian, Respuesta y BD_log.txt; conserva las carpetas.</p></div> : null}
          {step === 6 ? <div className="space-y-3"><p className="text-sm text-crema/70">Listo para activar</p><div className="rounded-[0.75rem] border border-musgo/20 p-4 text-xs text-crema/45"><p>SQL: {sqlLabel} · {server}</p><p className="mt-1">Raíz: {backupRoot}</p><p className="mt-1">Destino: {destinationEnabled ? `${destinationLabel} · ${destinationType.toUpperCase()}` : "Sólo ZIP local"}</p></div>{error ? <p className="text-xs text-red-400">{error}</p> : null}</div> : null}
        </div>
        <footer className="flex items-center justify-between border-t border-musgo/20 px-6 py-4"><button type="button" disabled={step === 0} onClick={() => setStep((value) => value - 1)} className="flex items-center gap-1 text-xs text-crema/40 disabled:opacity-20"><ChevronLeft size={14} /> Anterior</button>{step < STEPS.length - 1 ? <button type="button" onClick={() => setStep((value) => value + 1)} className="flex h-9 items-center gap-1 rounded-[0.5rem] bg-arcilla px-4 text-xs font-medium text-carbon">Siguiente <ChevronRight size={14} /></button> : <button type="button" onClick={activate} disabled={save.isPending} className="flex h-9 items-center gap-2 rounded-[0.5rem] bg-arcilla px-4 text-xs font-medium text-carbon disabled:opacity-40">{save.isPending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Activar perfiles</button>}</footer>
      </section>
    </div>
  );
}
