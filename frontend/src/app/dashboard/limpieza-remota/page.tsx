"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ShieldCheck, Server, Folder, File as FileIcon, RefreshCw, Loader2,
  AlertCircle, FlaskConical, Lock, ChevronRight,
  Archive, RotateCcw, History as HistoryIcon, ArrowRight, KeyRound, Boxes,
} from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { remoteCleanupService } from "@/services/remote-cleanup.service";
import { StructuralPanel } from "@/components/cleanup/structural-panel";
import type {
  CleanupServer, RemoteEntry, SimulationReport, SimRule,
  QuarantineItem, ExecutionRecord, RemoteCreds,
} from "@/types/remote-cleanup";

const INPUT = "w-full h-9 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-3 font-mono text-xs text-crema/75 placeholder:text-crema/25 focus:outline-none focus:border-arcilla/40 transition-colors";

function fmtDate(epoch: number | null) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString("es", { dateStyle: "short", timeStyle: "short" });
}

export default function LimpiezaRemotaPage() {
  const isAdmin = useAuthStore((s) => s.user?.role === "admin");

  const [servers, setServers]     = useState<CleanupServer[]>([]);
  const [serverId, setServerId]   = useState<string>("");
  // Credenciales — SOLO en memoria, nunca se persisten (ni contraseña ni llave .pem)
  const [authMethod, setAuthMethod] = useState<"password" | "pem">("password");
  const [password, setPassword]     = useState("");
  const [pemKey, setPemKey]         = useState("");   // contenido PEM de la llave privada
  const [pemName, setPemName]       = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [entries, setEntries]     = useState<RemoteEntry[]>([]);
  const [currentPath, setCurrent] = useState<string>("");
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineItem[]>([]);
  const [history, setHistory]       = useState<ExecutionRecord[]>([]);
  // Estructural (Ipsofactu, por defecto) vs por extensión/edad (navegación + reglas).
  const [cleanMode, setCleanMode]   = useState<"estructural" | "reglas">("estructural");
  // Sub-pestañas: separar OPERAR de auditar (cuarentena/historial).
  const [subtab, setSubtab]         = useState<"operar" | "cuarentena" | "historial">("operar");

  const server = servers.find((s) => s.id === serverId) ?? null;
  // La llave .pem solo aplica a SFTP; para FTP/FTPS se fuerza contraseña.
  const pemAvailable = (server?.protocol ?? "sftp") === "sftp";
  const effectiveMethod = pemAvailable ? authMethod : "password";
  const creds: RemoteCreds = effectiveMethod === "pem"
    ? { privateKey: pemKey, passphrase }
    : { password };

  function onPemFile(file: File | null) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { setPemKey(String(reader.result ?? "")); setPemName(file.name); };
    reader.readAsText(file);
  }

  const loadServers = useCallback(async () => {
    try {
      const { items } = await remoteCleanupService.listServers();
      setServers(items);
      if (items.length && !serverId) setServerId(items[0].id);
    } catch {}
  }, [serverId]);

  const loadAudit = useCallback(async () => {
    try {
      const [q, h] = await Promise.all([remoteCleanupService.quarantine(), remoteCleanupService.history()]);
      setQuarantine(q.items);
      setHistory(h.items);
    } catch {}
  }, []);

  useEffect(() => { loadServers(); loadAudit(); }, [loadServers, loadAudit]);

  async function doRestore(item: QuarantineItem) {
    try {
      await remoteCleanupService.restore(item.id, item.serverId, creds);
      loadAudit();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Error al restaurar");
    }
  }

  async function doList(path?: string) {
    if (!server) return;
    setLoading(true); setError(null);
    try {
      const res = await remoteCleanupService.list(server.id, creds, path);
      setEntries(res.entries);
      setCurrent(res.path);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Error al listar");
      setEntries([]);
    } finally { setLoading(false); }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Servidores Core</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Limpieza<span className="text-arcilla">.</span>
          </h1>
        </div>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-arcilla/80 border border-arcilla/30 bg-arcilla/10 rounded-full px-3 py-1">
          <ShieldCheck size={11} /> Simular → revisar → confirmar
        </span>
      </div>

      {/* Sub-pestañas: Operar · Cuarentena · Historial */}
      <div className="flex flex-wrap gap-1.5 border-b border-musgo/15 pb-3">
        <button onClick={() => setSubtab("operar")}
          className={cn("flex items-center gap-2 px-4 h-9 rounded-full font-mono text-xs transition-colors",
            subtab === "operar" ? "bg-arcilla/15 border border-arcilla/30 text-arcilla/90"
                                : "border border-transparent text-crema/40 hover:text-crema/70 hover:bg-musgo/10")}>
          <Boxes size={13} /> Operar
        </button>
        <button onClick={() => setSubtab("cuarentena")}
          className={cn("flex items-center gap-2 px-4 h-9 rounded-full font-mono text-xs transition-colors",
            subtab === "cuarentena" ? "bg-arcilla/15 border border-arcilla/30 text-arcilla/90"
                                    : "border border-transparent text-crema/40 hover:text-crema/70 hover:bg-musgo/10")}>
          <Archive size={13} /> Cuarentena
          {quarantine.length > 0 && <span className="text-[9px] text-crema/40">({quarantine.length})</span>}
        </button>
        <button onClick={() => setSubtab("historial")}
          className={cn("flex items-center gap-2 px-4 h-9 rounded-full font-mono text-xs transition-colors",
            subtab === "historial" ? "bg-arcilla/15 border border-arcilla/30 text-arcilla/90"
                                   : "border border-transparent text-crema/40 hover:text-crema/70 hover:bg-musgo/10")}>
          <HistoryIcon size={13} /> Historial
          {history.length > 0 && <span className="text-[9px] text-crema/40">({history.length})</span>}
        </button>
      </div>

      {/* ── OPERAR ── */}
      {subtab === "operar" && (servers.length === 0 ? (
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-10 text-center space-y-2">
          <Server size={22} className="text-crema/20 mx-auto" />
          <p className="font-sans text-sm text-crema/50">No hay servidores configurados</p>
          <p className="font-mono text-xs text-crema/25">
            {isAdmin
              ? "Ve a Configuración → Servidores para dar de alta un servidor y sus rutas autorizadas."
              : "Un administrador debe configurar los servidores y sus rutas autorizadas."}
          </p>
        </div>
      ) : (
        <>
          {/* Conexión */}
          <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-end">
              <div>
                <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1.5">Servidor</label>
                <select value={serverId} onChange={(e) => { setServerId(e.target.value); setEntries([]); setCurrent(""); }} className={INPUT}>
                  {servers.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} · {s.protocol}://{s.host}</option>
                  ))}
                </select>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider flex items-center gap-1">
                    <Lock size={9} /> Autenticación (no se guarda)
                  </label>
                  <div className="flex rounded-[0.375rem] border border-musgo/25 overflow-hidden">
                    <button onClick={() => setAuthMethod("password")}
                      className={cn("px-2 py-0.5 font-mono text-[9px] transition-colors",
                        effectiveMethod === "password" ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
                      Contraseña
                    </button>
                    <button onClick={() => pemAvailable && setAuthMethod("pem")} disabled={!pemAvailable}
                      title={pemAvailable ? "Llave privada .pem (AWS EC2)" : "Solo disponible con SFTP"}
                      className={cn("px-2 py-0.5 font-mono text-[9px] transition-colors disabled:opacity-30",
                        effectiveMethod === "pem" ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
                      Llave .pem
                    </button>
                  </div>
                </div>
                {effectiveMethod === "password" ? (
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT} placeholder="••••••••" />
                ) : (
                  <div className="grid grid-cols-[1fr_110px] gap-2">
                    <label className={cn(INPUT, "flex items-center gap-1.5 cursor-pointer hover:border-arcilla/40 overflow-hidden")}>
                      <KeyRound size={11} className="text-arcilla/60 shrink-0" />
                      <span className={cn("truncate", pemName ? "text-crema/75" : "text-crema/25")}>
                        {pemName || "Elegir archivo .pem…"}
                      </span>
                      <input type="file" className="hidden"
                        onChange={(e) => onPemFile(e.target.files?.[0] ?? null)} />
                    </label>
                    <input type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)}
                      className={INPUT} placeholder="Passphrase" title="Solo si la llave está cifrada" />
                  </div>
                )}
              </div>
              <button onClick={() => doList()} disabled={loading}
                className="h-9 px-4 rounded-[0.5rem] bg-arcilla/15 border border-arcilla/30 font-mono text-xs text-arcilla/90 hover:bg-arcilla/25 disabled:opacity-40 transition-colors flex items-center gap-2">
                {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Conectar / listar
              </button>
            </div>

            {/* Rutas autorizadas (puntos de entrada) */}
            {server && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="font-mono text-[10px] text-crema/30 mr-1 self-center">Rutas autorizadas:</span>
                {server.allowlist.length === 0 ? (
                  <span className="font-mono text-[10px] text-red-400/70">ninguna (bloqueado — configura la allowlist)</span>
                ) : server.allowlist.map((r) => (
                  <button key={r} onClick={() => doList(r)}
                    className="font-mono text-[10px] text-crema/60 border border-musgo/30 bg-musgo/10 rounded-full px-2.5 py-1 hover:border-arcilla/40 hover:text-crema/90 transition-colors">
                    {r}
                  </button>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-400 bg-red-400/[0.08] border border-red-400/[0.15] rounded-[0.75rem] px-4 py-3">
              <AlertCircle size={14} className="shrink-0" />
              <span className="font-mono text-xs">{error}</span>
            </div>
          )}

          {/* Selector de tipo de limpieza */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-crema/40 uppercase tracking-wider">Tipo de limpieza:</span>
            <div className="flex rounded-[0.5rem] border border-musgo/25 overflow-hidden">
              <button onClick={() => setCleanMode("estructural")}
                className={cn("px-3 h-8 font-mono text-[10px] transition-colors flex items-center gap-1",
                  cleanMode === "estructural" ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
                <Boxes size={11} /> Estructural (por propiedad)
              </button>
              <button onClick={() => setCleanMode("reglas")}
                className={cn("px-3 h-8 font-mono text-[10px] transition-colors flex items-center gap-1",
                  cleanMode === "reglas" ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
                <FlaskConical size={11} /> Por extensión/edad
              </button>
            </div>
          </div>

          {cleanMode === "estructural" && server && (
            <StructuralPanel server={server} creds={creds} onExecuted={loadAudit} />
          )}

          {/* Listado + Simulación (modo por extensión/edad) */}
          {cleanMode === "reglas" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
            {/* Tabla de archivos */}
            <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-musgo/15 flex items-center gap-2">
                <Folder size={12} className="text-arcilla/60" />
                <span className="font-mono text-[11px] text-crema/50 truncate">{currentPath || "— selecciona una ruta autorizada —"}</span>
              </div>
              {entries.length === 0 ? (
                <div className="p-10 text-center font-mono text-xs text-crema/25">
                  {currentPath ? "Carpeta vacía" : "Sin datos"}
                </div>
              ) : (
                <div className="divide-y divide-musgo/10 max-h-[420px] overflow-y-auto">
                  {entries.map((e) => (
                    <div key={e.path}
                      className={cn("grid grid-cols-[1fr_90px_140px] gap-2 px-4 py-2.5 items-center",
                        e.isDir ? "cursor-pointer hover:bg-musgo/10" : "")}
                      onClick={() => e.isDir && doList(e.path)}>
                      <div className="flex items-center gap-2 min-w-0">
                        {e.isDir ? <Folder size={13} className="text-arcilla/60 shrink-0" /> : <FileIcon size={13} className="text-crema/30 shrink-0" />}
                        <span className="font-mono text-xs text-crema/75 truncate">{e.name}</span>
                        {e.isDir && <ChevronRight size={11} className="text-crema/20 shrink-0" />}
                      </div>
                      <span className="font-mono text-[11px] text-crema/40 text-right">{e.isDir ? "—" : formatBytes(e.sizeBytes)}</span>
                      <span className="font-mono text-[10px] text-crema/30 text-right">{fmtDate(e.modified)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Panel de simulación + ejecución */}
            {server && <SimulationPanel server={server} creds={creds} onExecuted={loadAudit} />}
          </div>
          )}
        </>
      ))}

      {/* ── CUARENTENA ── */}
      {subtab === "cuarentena" && (
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          <div className="flex items-center gap-2 mb-3">
            <Archive size={13} className="text-arcilla/70" />
            <span className="font-sans text-sm font-medium text-crema/75">Cuarentena</span>
            <span className="font-mono text-[10px] text-crema/30">({quarantine.length})</span>
          </div>
          <p className="font-mono text-[10px] text-crema/30 mb-3">Archivos movidos (reversibles). No se han eliminado.</p>
          {quarantine.length === 0 ? (
            <p className="font-mono text-xs text-crema/25 py-4 text-center">Cuarentena vacía</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {quarantine.map((q) => (
                <div key={q.id} className="flex items-center gap-2 px-3 py-2 rounded-[0.5rem] bg-musgo/5 border border-musgo/15">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[11px] text-crema/70 truncate">{q.name}</p>
                    <p className="font-mono text-[9px] text-crema/25 truncate">{q.originalPath}</p>
                  </div>
                  <span className="font-mono text-[9px] text-crema/30 shrink-0">{formatBytes(q.sizeBytes)}</span>
                  {isAdmin && (
                    <button onClick={() => doRestore(q)} title="Restaurar a su ruta original"
                      className="flex items-center gap-1 px-2 py-1 rounded-[0.375rem] bg-musgo/20 border border-musgo/30 font-mono text-[9px] text-crema/50 hover:text-crema/80 transition-colors shrink-0">
                      <RotateCcw size={10} /> Restaurar
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── HISTORIAL ── */}
      {subtab === "historial" && (
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          <div className="flex items-center gap-2 mb-3">
            <HistoryIcon size={13} className="text-arcilla/70" />
            <span className="font-sans text-sm font-medium text-crema/75">Historial de ejecuciones</span>
            <span className="font-mono text-[10px] text-crema/30">({history.length})</span>
          </div>
          {history.length === 0 ? (
            <p className="font-mono text-xs text-crema/25 py-4 text-center">Sin ejecuciones aún</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {history.map((h) => (
                <div key={h.id} className="px-3 py-2 rounded-[0.5rem] bg-musgo/5 border border-musgo/15">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-crema/70 truncate">{h.serverName} · {h.actor}</span>
                    <span className={cn("font-mono text-[9px] px-1.5 py-0.5 rounded-full border shrink-0",
                      h.estado === "completado" ? "text-green-400/80 border-green-800/40 bg-green-900/10"
                                                : "text-orange-400/80 border-orange-800/40 bg-orange-900/10")}>
                      {h.estado}
                    </span>
                  </div>
                  <p className="font-mono text-[9px] text-crema/30 mt-1">
                    {h.movidos} movidos · {h.omitidos} omitidos · {h.fallidos} fallidos · {formatBytes(h.espacioBytes)} ·{" "}
                    {new Date(h.startedAt).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Panel de simulación (Fase 3) ────────────────────────────────────────────────
function SimulationPanel({ server, creds, onExecuted }: { server: CleanupServer; creds: RemoteCreds; onExecuted: () => void }) {
  const [extCsv, setExtCsv]   = useState(".log,.tmp");
  const [minAge, setMinAge]   = useState(30);
  const [report, setReport]   = useState<SimulationReport | null>(null);
  const [lastRule, setLastRule] = useState<SimRule | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [executing, setExecuting]     = useState(false);
  const [execMsg, setExecMsg]         = useState<string | null>(null);

  async function run() {
    setLoading(true); setError(null); setReport(null); setExecMsg(null); setConfirmText("");
    const rule: SimRule = {
      rutasPermitidas: server.allowlist,
      extensionesPermitidas: extCsv.split(",").map((s) => s.trim()).filter(Boolean),
      antiguedadMinimaDias: minAge,
      noModificadoUltimasHoras: 24,
    };
    setLastRule(rule);
    try {
      setReport(await remoteCleanupService.simulate(server.id, creds, rule));
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Error en la simulación");
    } finally { setLoading(false); }
  }

  async function execute() {
    if (!report || !lastRule) return;
    setExecuting(true); setExecMsg(null); setError(null);
    try {
      const res: any = await remoteCleanupService.execute(server.id, creds, lastRule, report.elegiblesCount);
      setExecMsg(`Movidos a cuarentena: ${res.movidos} · fallidos: ${res.fallidos}`);
      setReport(null); setConfirmText("");
      onExecuted();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Error al ejecutar");
    } finally { setExecuting(false); }
  }

  return (
    <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5 space-y-3 self-start">
      <div className="flex items-center gap-2">
        <FlaskConical size={13} className="text-arcilla/70" />
        <span className="font-sans text-sm font-medium text-crema/75">Simular limpieza</span>
      </div>
      <p className="font-mono text-[10px] text-crema/30 leading-relaxed">
        Recorre las rutas autorizadas y calcula qué se eliminaría. <span className="text-green-400/70">No borra nada.</span>
      </p>

      <div>
        <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Extensiones</label>
        <input value={extCsv} onChange={(e) => setExtCsv(e.target.value)} className={INPUT} placeholder=".log,.tmp,.xml" />
      </div>
      <div>
        <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">Antigüedad mínima (días)</label>
        <input type="number" min={0} value={minAge} onChange={(e) => setMinAge(Number(e.target.value))} className={INPUT} />
      </div>

      <button onClick={run} disabled={loading || server.allowlist.length === 0}
        className="w-full h-9 rounded-[0.5rem] bg-arcilla/15 border border-arcilla/30 font-mono text-xs text-arcilla/90 hover:bg-arcilla/25 disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
        {loading ? <><Loader2 size={12} className="animate-spin" /> Simulando…</> : "Simular ahora"}
      </button>

      {error && <p className="font-mono text-[11px] text-red-400/80">{error}</p>}

      {report && (
        <div className="pt-2 border-t border-musgo/15 space-y-2">
          <span className="inline-block font-mono text-[9px] text-green-400/80 border border-green-800/40 bg-green-900/10 rounded-full px-2 py-0.5">
            SIMULACIÓN — no se eliminó nada
          </span>
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <Stat label="Encontrados" value={report.encontrados} />
            <Stat label="Elegibles" value={report.elegiblesCount} accent />
            <Stat label="Se liberaría" value={formatBytes(report.espacioLiberadoBytes)} accent />
            <Stat label="Excluidos" value={report.excluidosCount} />
            <Stat label="Protegidos" value={report.protegidosCount} />
            {report.truncated && <Stat label="Truncado" value="sí" />}
          </div>

          {report.excluidos.length > 0 && (
            <details className="mt-1">
              <summary className="font-mono text-[10px] text-crema/40 cursor-pointer hover:text-crema/70">Ver motivos de exclusión</summary>
              <div className="mt-1.5 max-h-40 overflow-y-auto space-y-1">
                {report.excluidos.slice(0, 100).map((x, i) => (
                  <div key={i} className="font-mono text-[9px] text-crema/40 flex justify-between gap-2">
                    <span className="truncate">{x.path.split("/").pop()}</span>
                    <span className="text-crema/25 shrink-0">{x.reason}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {report.warnings.map((w, i) => (
            <p key={i} className="font-mono text-[10px] text-orange-400/70">⚠ {w}</p>
          ))}

          {report.elegiblesCount > 0 && (
            <div className="pt-2 mt-1 border-t border-musgo/15 space-y-2">
              <p className="font-mono text-[10px] text-crema/45 leading-relaxed">
                Mover {report.elegiblesCount} archivo(s) a <span className="text-arcilla/80">cuarentena</span> (reversible,
                no se elimina). Escribe <span className="text-crema/85 font-bold">MOVER</span> para confirmar:
              </p>
              <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="MOVER" className={INPUT} />
              <button onClick={execute} disabled={executing || confirmText.trim().toUpperCase() !== "MOVER"}
                className="w-full h-9 rounded-[0.5rem] bg-red-900/25 border border-red-800/40 font-mono text-xs text-red-200 hover:bg-red-900/40 disabled:opacity-30 transition-colors flex items-center justify-center gap-2">
                {executing ? <><Loader2 size={12} className="animate-spin" /> Moviendo…</> : <><Archive size={12} /> Mover a cuarentena</>}
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

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) {
  return (
    <div className="rounded-[0.5rem] bg-carbon/40 border border-musgo/15 px-2.5 py-1.5">
      <p className={cn("font-display text-lg italic font-light", accent ? "text-arcilla" : "text-crema/85")}>{value}</p>
      <p className="text-[9px] text-crema/35 uppercase tracking-wider">{label}</p>
    </div>
  );
}

