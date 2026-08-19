"use client";

import { useEffect, useRef, useState } from "react";
import {
  Boxes, Loader2, FlaskConical, Archive, Trash2, ArrowRight, AlertTriangle, XCircle,
} from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";
import { remoteCleanupService } from "@/services/remote-cleanup.service";
import type {
  CleanupServer, RemoteCreds, StructuralRule, StructuralReport, CleanupJob,
} from "@/types/remote-cleanup";

const INPUT =
  "w-full h-9 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-3 font-mono text-xs text-crema/75 placeholder:text-crema/25 focus:outline-none focus:border-arcilla/40 transition-colors";

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) {
  return (
    <div className="rounded-[0.5rem] bg-carbon/40 border border-musgo/15 px-2.5 py-1.5">
      <p className={cn("font-display text-lg italic font-light", accent ? "text-arcilla" : "text-crema/85")}>{value}</p>
      <p className="text-[9px] text-crema/35 uppercase tracking-wider">{label}</p>
    </div>
  );
}

/**
 * Panel de limpieza ESTRUCTURAL (Ipsofactu): vacía core/{Log,LogSec,LogsRadian,Respuesta}
 * y borra core/BD_log.txt en cada propiedad bajo la raíz. Simulación obligatoria antes de
 * ejecutar; modo cuarentena (reversible) o directo (borra). Límite de propiedades para
 * probar por lotes mientras se afinan las reglas.
 */
export function StructuralPanel({
  server, creds, onExecuted,
}: { server: CleanupServer; creds: RemoteCreds; onExecuted: () => void }) {
  const [carpetas, setCarpetas]   = useState("Log, LogSec, LogsRadian, Respuesta");
  const [archivos, setArchivos]   = useState("BD_log.txt");
  const [contenedora, setCont]    = useState("core");
  const [maxProps, setMaxProps]   = useState(0);   // 0 = todas
  const [maxFiles, setMaxFiles]   = useState(50000);
  const [maxGb, setMaxGb]         = useState(20);
  const [report, setReport]       = useState<StructuralReport | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const [modo, setModo]           = useState<"cuarentena" | "directo">("cuarentena");
  const [confirmText, setConfirm] = useState("");
  const [executing, setExecuting] = useState(false);
  const [execMsg, setExecMsg]     = useState<string | null>(null);
  const isAgent = server.transport === "agent" && !!server.agentId;

  useEffect(() => {
    if (!isAgent) return;
    setCarpetas((server.targetFolders ?? []).join(", "));
    setArchivos((server.targetFiles ?? []).join(", "));
    setModo("directo");
    setReport(null);
  }, [isAgent, server.id, server.targetFiles, server.targetFolders]);

  // Job en segundo plano: progreso + cancelación
  const [progress, setProgress] = useState<{ proc: number; total: number; enc: number; fase: string } | null>(null);
  const jobIdRef = useRef<string | null>(null);

  async function pollJob(jobId: string): Promise<CleanupJob> {
    jobIdRef.current = jobId;
    // Poll hasta que el job deje de estar "running".
    while (true) {
      const j = await remoteCleanupService.structuralJob(jobId);
      setProgress({ proc: j.propiedadesProcesadas, total: j.propiedadesTotales, enc: j.encontrados, fase: j.fase });
      if (j.status !== "running") { jobIdRef.current = null; return j; }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function pollAgentJob(jobId: string) {
    jobIdRef.current = jobId;
    for (let attempt = 0; attempt < 240; attempt += 1) {
      const job = await remoteCleanupService.agentJob(jobId);
      setProgress({
        proc: job.processedUnits,
        total: job.totalUnits,
        enc: job.foundCount,
        fase: job.phase,
      });
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        jobIdRef.current = null;
        return job;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new Error("El agente no respondio dentro del tiempo esperado");
  }

  async function cancel() {
    const jid = jobIdRef.current;
    if (jid) {
      try {
        if (isAgent) await remoteCleanupService.agentJobCancel(jid);
        else await remoteCleanupService.structuralJobCancel(jid);
      } catch {}
    }
  }

  const csv = (s: string) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
  const buildRule = (): StructuralRule => ({
    tipo: "estructural",
    raiz: server.rutaBase,
    carpetaContenedora: contenedora.trim() || "core",
    vaciarCarpetas: csv(carpetas),
    borrarArchivos: csv(archivos),
  });

  const confirmWord = modo === "directo" ? "BORRAR" : "MOVER";

  async function run() {
    setLoading(true); setError(null); setReport(null); setExecMsg(null); setConfirm(""); setProgress(null);
    try {
      if (isAgent) {
        const { jobId } = await remoteCleanupService.agentStructuralSimulate(
          server.agentId!, server.id, contenedora.trim() || "Core", maxProps,
          maxFiles, Math.round(maxGb * 1024 ** 3),
        );
        const job = await pollAgentJob(jobId);
        setProgress(null);
        if (job.status === "failed") throw new Error(job.error ?? "Error en la simulacion");
        if (job.status === "cancelled") throw new Error("Simulacion cancelada");
        const value = job.result ?? {};
        const samples = (value.samples ?? []) as Array<Record<string, any>>;
        const perProperty = (value.byProperty ?? {}) as Record<string, number>;
        setReport({
          simulationId: String(value.simulationId ?? ""),
          manifestHash: String(value.manifestHash ?? ""),
          simulacion: true,
          encontrados: Number(value.eligibleCount ?? 0),
          elegibles: samples.map((item) => ({
            name: String(item.relativePath ?? item.path ?? "").split(/[\\/]/).pop() ?? "",
            path: String(item.path ?? ""),
            sizeBytes: Number(item.sizeBytes ?? 0),
            modified: null,
            isDir: false,
            permissions: null,
          })),
          elegiblesCount: Number(value.eligibleCount ?? 0),
          espacioLiberadoBytes: Number(value.bytesEligible ?? 0),
          excluidos: [],
          excluidosCount: 0,
          protegidos: (value.protected ?? []) as any,
          protegidosCount: Number(value.protectedCount ?? 0),
          propiedadesAfectadas: Number(value.propertiesAffected ?? Object.keys(perProperty).length),
          porPropiedad: perProperty,
          propiedadesTotales: Number(value.propertiesProcessed ?? 0),
          propiedadesConCore: Number(value.propertiesAffected ?? Object.keys(perProperty).length),
          truncated: Boolean(value.truncated),
          raiz: String(value.root ?? server.rutaBase),
          warnings: samples.length < Number(value.eligibleCount ?? 0)
            ? ["La vista muestra una muestra; la ejecucion usa el manifiesto completo validado por el agente."]
            : [],
        });
        return;
      }
      const { jobId } = await remoteCleanupService.structuralSimulate(server.id, creds, buildRule(), maxProps);
      const job = await pollJob(jobId);
      setProgress(null);
      if (job.status === "error") setError(job.error ?? "Error en la simulación");
      else if (job.status === "cancelado") setError("Simulación cancelada.");
      else setReport(job.result as StructuralReport);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Error en la simulación");
    } finally { setLoading(false); }
  }

  async function execute() {
    if (!report) return;
    setExecuting(true); setExecMsg(null); setError(null); setProgress(null);
    try {
      if (isAgent) {
        if (!report.simulationId || !report.manifestHash) throw new Error("La simulacion del agente no es valida");
        const { jobId } = await remoteCleanupService.agentStructuralExecuteDirect(
          server.agentId!, report.simulationId, report.manifestHash,
        );
        const job = await pollAgentJob(jobId);
        setProgress(null);
        if (job.status === "failed") throw new Error(job.error ?? "Error al ejecutar");
        const value = job.result ?? {};
        setExecMsg(`Logs eliminados: ${value.deletedCount ?? 0} · omitidos: ${value.failedCount ?? 0} · espacio liberado: ${formatBytes(Number(value.bytesDeleted ?? 0))}`);
        setReport(null); setConfirm("");
        onExecuted();
        return;
      }
      const { jobId } = await remoteCleanupService.structuralExecute(
        server.id, creds, buildRule(), modo, report.elegiblesCount, maxProps,
      );
      const job = await pollJob(jobId);
      setProgress(null);
      if (job.status === "error") { setError(job.error ?? "Error al ejecutar"); return; }
      const res: any = job.result ?? {};
      const cancelNote = job.status === "cancelado" ? " (cancelado)" : "";
      setExecMsg(
        modo === "directo"
          ? `Borrados: ${res.borrados ?? 0} · fallidos: ${res.fallidos ?? 0} · ${res.propiedadesAfectadas ?? 0} propiedad(es)${cancelNote}`
          : `Movidos a cuarentena: ${res.movidos ?? 0} · fallidos: ${res.fallidos ?? 0} · ${res.propiedadesAfectadas ?? 0} propiedad(es)${cancelNote}`,
      );
      setReport(null); setConfirm("");
      onExecuted();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Error al ejecutar");
    } finally { setExecuting(false); }
  }

  const porPropiedad = report ? Object.entries(report.porPropiedad).sort((a, b) => b[1] - a[1]) : [];

  return (
    <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Boxes size={14} className="text-arcilla/70" />
        <span className="font-sans text-sm font-medium text-crema/75">Limpieza estructural (por propiedad)</span>
      </div>
      <p className="font-mono text-[10px] text-crema/35 leading-relaxed">
        Recorre cada propiedad bajo <span className="text-crema/70">{server.rutaBase || "la raíz"}</span>, entra a{" "}
        <span className="text-arcilla/80">{contenedora || "core"}</span> y vacía las carpetas indicadas + borra los
        archivos indicados. <span className="text-green-400/70">La simulación no borra nada.</span>
      </p>

      {/* Configuración de la regla */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="md:col-span-2">
          <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">
            Carpetas a vaciar (separadas por coma) — se conserva la carpeta, se borra su contenido
          </label>
          <input value={carpetas} onChange={(e) => setCarpetas(e.target.value)} disabled={isAgent} className={INPUT}
            placeholder="Log, LogSec, LogsRadian, Respuesta" />
        </div>
        <div>
          <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Archivos a borrar</label>
          <input value={archivos} onChange={(e) => setArchivos(e.target.value)} disabled={isAgent} className={INPUT} placeholder="BD_log.txt" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Carpeta contenedora</label>
            <input value={contenedora} onChange={(e) => setCont(e.target.value)} className={INPUT} placeholder="core" />
          </div>
          <div>
            <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1" title="0 = todas las propiedades">
              Límite propiedades
            </label>
            <input type="number" min={0} value={maxProps} onChange={(e) => setMaxProps(Number(e.target.value))} className={INPUT} />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Máximo de archivos</label>
          <input type="number" min={0} max={200000} value={maxFiles}
            onChange={(e) => setMaxFiles(Math.max(0, Number(e.target.value)))} className={INPUT} />
        </div>
        <div>
          <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Máximo por ejecución (GB)</label>
          <input type="number" min={0} max={1024} step={1} value={maxGb}
            onChange={(e) => setMaxGb(Math.max(0, Number(e.target.value)))} className={INPUT} />
        </div>
      </div>
      <p className="font-mono text-[9px] text-crema/30 -mt-1">
        Límite de propiedades: <span className="text-crema/50">0 = todas</span>. Pon un número (ej. 5) para probar en pocas
        mientras afinas las reglas. En archivos y GB, <span className="text-crema/50">0 = sin límite</span>.
      </p>

      <button onClick={run} disabled={loading || executing}
        className="w-full h-9 rounded-[0.5rem] bg-arcilla/15 border border-arcilla/30 font-mono text-xs text-arcilla/90 hover:bg-arcilla/25 disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
        {loading ? <><Loader2 size={12} className="animate-spin" /> Simulando…</> : <><FlaskConical size={12} /> Simular</>}
      </button>

      {/* Progreso del job en segundo plano */}
      {progress && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between font-mono text-[10px] text-crema/50">
            <span className="capitalize">{progress.fase}… {progress.proc}/{progress.total || "?"} propiedades</span>
            <span>{progress.enc} archivo(s)</span>
          </div>
          <div className="h-1.5 bg-musgo/20 rounded-full overflow-hidden">
            <div className="h-full bg-arcilla transition-all"
              style={{ width: `${progress.total ? Math.min(100, (progress.proc / progress.total) * 100) : 5}%` }} />
          </div>
          {!isAgent && <button onClick={cancel}
            className="flex items-center gap-1 font-mono text-[10px] text-crema/40 hover:text-red-400 transition-colors">
            <XCircle size={11} /> Cancelar
          </button>}
        </div>
      )}

      {error && <p className="font-mono text-[11px] text-red-400/80">{error}</p>}

      {report && (
        <div className="pt-2 border-t border-musgo/15 space-y-3">
          <span className="inline-block font-mono text-[9px] text-green-400/80 border border-green-800/40 bg-green-900/10 rounded-full px-2 py-0.5">
            SIMULACIÓN — no se eliminó nada
          </span>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 font-mono text-[11px]">
            <Stat label="Encontrados" value={report.encontrados} />
            <Stat label="Elegibles" value={report.elegiblesCount} accent />
            <Stat label="Se liberaría" value={formatBytes(report.espacioLiberadoBytes)} accent />
            <Stat label="Propiedades afectadas" value={report.propiedadesAfectadas} />
            <Stat label="Protegidos" value={report.protegidosCount} />
            {report.propiedadesTotales != null && <Stat label="Props. recorridas" value={`${report.propiedadesConCore ?? 0}/${report.propiedadesTotales}`} />}
          </div>

          {report.truncated && (
            <p className="font-mono text-[10px] text-orange-400/80 flex items-center gap-1">
              <AlertTriangle size={11} /> Recorrido truncado — usa el límite de propiedades para revisar por lotes.
            </p>
          )}
          {report.warnings?.map((w, i) => (
            <p key={i} className="font-mono text-[10px] text-orange-400/70">⚠ {w}</p>
          ))}

          {/* Desglose por propiedad */}
          {porPropiedad.length > 0 && (
            <details className="mt-1">
              <summary className="font-mono text-[10px] text-crema/40 cursor-pointer hover:text-crema/70">
                Ver desglose por propiedad ({porPropiedad.length})
              </summary>
              <div className="mt-1.5 max-h-44 overflow-y-auto space-y-0.5">
                {porPropiedad.map(([prop, n]) => (
                  <div key={prop} className="font-mono text-[10px] text-crema/50 flex justify-between gap-2 px-1">
                    <span className="truncate">{prop}</span>
                    <span className="text-crema/30 shrink-0">{n} archivo(s)</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {report.protegidos?.length > 0 && (
            <details>
              <summary className="font-mono text-[10px] text-crema/40 cursor-pointer hover:text-crema/70">
                Ver protegidos ({report.protegidos.length}) — no se borrarán
              </summary>
              <div className="mt-1.5 max-h-32 overflow-y-auto space-y-1">
                {report.protegidos.slice(0, 100).map((x, i) => (
                  <div key={i} className="font-mono text-[9px] text-crema/40 flex justify-between gap-2">
                    <span className="truncate">{x.path.split("/").pop()}</span>
                    <span className="text-crema/25 shrink-0">{x.reason}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Ejecución */}
          {report.elegiblesCount > 0 && (
            <div className="pt-3 mt-1 border-t border-musgo/15 space-y-2.5">
              {/* Los servidores por agente eliminan logs directamente. El modo heredado conserva ambas opciones. */}
              {!isAgent && <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-crema/40 uppercase tracking-wider">Modo:</span>
                <div className="flex rounded-[0.5rem] border border-musgo/25 overflow-hidden">
                  <button onClick={() => { setModo("cuarentena"); setConfirm(""); }}
                    className={cn("px-3 py-1 font-mono text-[10px] transition-colors flex items-center gap-1",
                      modo === "cuarentena" ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
                    <Archive size={10} /> Cuarentena
                  </button>
                  <button onClick={() => { if (!isAgent) setModo("directo"); setConfirm(""); }} disabled={isAgent}
                    className={cn("px-3 py-1 font-mono text-[10px] transition-colors flex items-center gap-1",
                      modo === "directo" ? "bg-red-900/40 text-red-200" : "text-crema/35 hover:text-crema/55", isAgent && "opacity-30")}>
                    <Trash2 size={10} /> Directo
                  </button>
                </div>
              </div>}
              {!isAgent && <p className="font-mono text-[10px] text-crema/45 leading-relaxed">
                {modo === "cuarentena" ? (
                  <>Mover <span className="text-arcilla/80">{report.elegiblesCount}</span> archivo(s) a cuarentena
                    (reversible). Escribe <span className="text-crema/85 font-bold">MOVER</span> para confirmar:</>
                ) : (
                  <span className="text-red-300/90">Borrar <span className="font-bold">{report.elegiblesCount}</span> archivo(s)
                    de forma <span className="font-bold">DEFINITIVA</span> (sin vuelta atrás) en{" "}
                    {report.propiedadesAfectadas} propiedad(es). Escribe <span className="font-bold">BORRAR</span> para confirmar:</span>
                )}
              </p>}
              {!isAgent && <input value={confirmText} onChange={(e) => setConfirm(e.target.value)} placeholder={confirmWord} className={INPUT} />}
              <button onClick={execute} disabled={executing || (!isAgent && confirmText.trim().toUpperCase() !== confirmWord)}
                className={cn(
                  "w-full h-9 rounded-[0.5rem] border font-mono text-xs transition-colors flex items-center justify-center gap-2 disabled:opacity-30",
                  modo === "directo"
                    ? "bg-red-900/30 border-red-800/50 text-red-200 hover:bg-red-900/50"
                    : "bg-arcilla/15 border-arcilla/30 text-arcilla/90 hover:bg-arcilla/25",
                )}>
                {executing
                  ? <><Loader2 size={12} className="animate-spin" /> {modo === "directo" ? "Borrando…" : "Moviendo…"}</>
                  : modo === "directo" ? <><Trash2 size={12} /> Eliminar logs</> : <><Archive size={12} /> Mover a cuarentena</>}
              </button>
            </div>
          )}
        </div>
      )}

      {execMsg && (
        <p className="font-mono text-[11px] text-green-400/80 flex items-center gap-1.5 pt-1">
          <ArrowRight size={11} /> {execMsg}
        </p>
      )}
    </div>
  );
}
