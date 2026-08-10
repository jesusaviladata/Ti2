"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Monitor, Plus, X, Loader2, AlertTriangle,
  Clock, Wifi, WifiOff, User, Server, Shield,
  ShieldAlert, Download, ChevronDown, CheckCircle2, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDialog } from "@/hooks/useDialog";
import { accessService } from "@/services/access.service";
import type { AccessSession, CreateSessionPayload } from "@/types/access";
import { ContextMenuPortal } from "@/components/ui/context-menu-portal";

// ── Constants ─────────────────────────────────────────────────────────────────
const SERVERS   = ["Servidor 224", "Servidor DX", "Servidor 233"];
const ENGINEERS = ["Alan Hernandez", "Geovanni", "Luis"];

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDuration(min: number | null): string {
  if (min === null) return "—";
  if (min < 60) return `${min}m`;
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("es", { timeStyle: "short" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("es", { dateStyle: "short", timeStyle: "short" });
}

function elapsed(start: string): string {
  const diff = Math.floor((Date.now() - new Date(start).getTime()) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
}

// ── Dropdown ──────────────────────────────────────────────────────────────────
function Dropdown({ label, options, value, onChange }: {
  label:    string;
  options:  string[];
  value:    string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <p className="font-mono text-[10px] text-crema/35 uppercase tracking-wider mb-1.5">{label}</p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        className={cn(
          "w-full h-9 flex items-center justify-between px-3",
          "bg-musgo/10 border border-musgo/25 rounded-[0.5rem]",
          "font-mono text-xs transition-colors",
          value ? "text-crema/75" : "text-crema/25",
          open ? "border-arcilla/40" : "hover:border-musgo/45"
        )}
      >
        <span>{value || `Seleccionar ${label.toLowerCase()}`}</span>
        <ChevronDown size={11} className={cn("text-crema/30 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute left-0 top-full mt-1 z-50 w-full rounded-[0.625rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden"
        >
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              role="option"
              aria-selected={value === opt}
              onClick={() => { onChange(opt); setOpen(false); }}
              className={cn(
                "w-full text-left px-3 py-2 font-mono text-xs transition-colors",
                value === opt
                  ? "bg-arcilla/10 text-arcilla/80"
                  : "text-crema/60 hover:bg-musgo/15"
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── New Session Modal ─────────────────────────────────────────────────────────
function NewSessionModal({ onClose, onCreated }: {
  onClose:   () => void;
  onCreated: (s: AccessSession) => void;
}) {
  const [server,   setServer]   = useState("");
  const [engineer, setEngineer] = useState("");
  const [reason,   setReason]   = useState("");
  const [client,   setClient]   = useState("");
  const [startAt]               = useState(() => new Date());
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const dialogRef = useDialog(true, onClose);

  async function handleSubmit() {
    if (!server)   { setError("Selecciona un servidor");   return; }
    if (!engineer) { setError("Selecciona un ingeniero");  return; }
    if (!reason.trim()) { setError("Ingresa el motivo");   return; }
    if (!client.trim()) { setError("Ingresa el cliente");  return; }
    setLoading(true); setError("");
    try {
      const payload: CreateSessionPayload = {
        server,
        ip:     "",
        tool:   "RDP",
        reason,
        client,
        engineer,
      };
      const session = await accessService.createSession(payload);
      onCreated(session);
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Error");
    } finally {
      setLoading(false);
    }
  }

  const INPUT = "w-full h-9 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-3 font-mono text-xs text-crema/75 placeholder:text-crema/20 focus:outline-none focus:border-arcilla/40 transition-colors";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="newsession-title"
        className="relative z-10 w-full max-w-md rounded-[1.25rem] border border-musgo/30 bg-carbon shadow-2xl p-6"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Monitor size={15} className="text-arcilla/70" />
            <span id="newsession-title" className="font-mono text-sm text-crema/80">Nueva sesión remota</span>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="text-crema/25 hover:text-crema/60 transition-colors">
            <X size={15} />
          </button>
        </div>

        <div className="space-y-3">
          {/* Server */}
          <Dropdown label="Servidor" options={SERVERS} value={server} onChange={setServer} />

          {/* Engineer */}
          <Dropdown label="Ingeniero solicitante" options={ENGINEERS} value={engineer} onChange={setEngineer} />

          {/* Reason */}
          <div>
            <p className="font-mono text-[10px] text-crema/35 uppercase tracking-wider mb-1.5">Motivo</p>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe el motivo del acceso"
              className={INPUT}
            />
          </div>

          {/* Client */}
          <div>
            <p className="font-mono text-[10px] text-crema/35 uppercase tracking-wider mb-1.5">Cliente</p>
            <input
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Nombre del cliente"
              className={INPUT}
            />
          </div>

          {/* Start time */}
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-[0.5rem] bg-musgo/10 border border-musgo/20">
            <Clock size={12} className="text-crema/30 shrink-0" />
            <span className="font-mono text-[10px] text-crema/35 uppercase tracking-wider">Hora de inicio</span>
            <span className="font-mono text-xs text-crema/70 ml-auto">
              {startAt.toLocaleTimeString("es", { timeStyle: "short" })}
            </span>
          </div>

          {error && (
            <p className="font-mono text-[10px] text-red-400/80 bg-red-900/10 border border-red-700/25 rounded-[0.5rem] px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex gap-2 pt-1">
            <button onClick={onClose}
              className="flex-1 h-9 rounded-[0.75rem] border border-musgo/25 font-mono text-xs text-crema/40 hover:text-crema/70 transition-colors">
              Cancelar
            </button>
            <button onClick={handleSubmit} disabled={loading}
              className="flex-1 h-9 rounded-[0.75rem] bg-arcilla/10 border border-arcilla/35 font-mono text-xs text-arcilla/80 hover:bg-arcilla/15 disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
              {loading ? <Loader2 size={13} className="animate-spin" /> : <Wifi size={13} />}
              Iniciar sesión
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Terminate Modal ───────────────────────────────────────────────────────────
function TerminateModal({ session, onClose, onClosed }: {
  session:  AccessSession;
  onClose:  () => void;
  onClosed: (s: AccessSession) => void;
}) {
  const [notes,   setNotes]   = useState("");
  const [loading, setLoading] = useState(false);
  const [endTime] = useState(() => new Date());

  async function handleTerminate() {
    setLoading(true);
    try {
      const updated = await accessService.closeSession(session.id, notes);
      onClosed(updated);
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-sm rounded-[1.25rem] border border-red-800/40 bg-carbon shadow-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <WifiOff size={15} className="text-red-400/70" />
          <span className="font-mono text-sm text-crema/80">Confirmar término de sesión</span>
        </div>

        {/* Summary */}
        <div className="rounded-[0.75rem] border border-musgo/20 bg-musgo/10 p-3 space-y-2 mb-4">
          <div className="flex justify-between">
            <span className="font-mono text-[10px] text-crema/30 uppercase tracking-wider">Servidor</span>
            <span className="font-mono text-xs text-crema/70">{session.server}</span>
          </div>
          <div className="flex justify-between">
            <span className="font-mono text-[10px] text-crema/30 uppercase tracking-wider">Ingeniero</span>
            <span className="font-mono text-xs text-crema/70">{(session as any).engineer ?? session.user}</span>
          </div>
          <div className="flex justify-between">
            <span className="font-mono text-[10px] text-crema/30 uppercase tracking-wider">Hora inicio</span>
            <span className="font-mono text-xs text-crema/70">{formatTime(session.start)}</span>
          </div>
          <div className="flex justify-between border-t border-musgo/15 pt-2">
            <span className="font-mono text-[10px] text-red-400/60 uppercase tracking-wider">Hora término</span>
            <span className="font-mono text-xs text-red-400/80 font-medium">
              {endTime.toLocaleTimeString("es", { timeStyle: "short" })}
            </span>
          </div>
        </div>

        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notas adicionales (opcional)"
          rows={2}
          className="w-full bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-3 py-2 font-mono text-xs text-crema/75 placeholder:text-crema/20 focus:outline-none focus:border-red-800/40 transition-colors resize-none mb-4"
        />

        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 h-9 rounded-[0.75rem] border border-musgo/25 font-mono text-xs text-crema/40 hover:text-crema/70 transition-colors">
            Cancelar
          </button>
          <button onClick={handleTerminate} disabled={loading}
            className="flex-1 h-9 rounded-[0.75rem] bg-red-900/20 border border-red-700/40 font-mono text-xs text-red-400 hover:bg-red-900/30 disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
            {loading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
            Terminado
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Session Card ──────────────────────────────────────────────────────────────
interface CtxState { x: number; y: number }

function SessionCard({ session, onTerminate, onDelete }: {
  session:     AccessSession;
  onTerminate?: () => void;
  onDelete?:   () => void;
}) {
  const [, setTick] = useState(0);
  const [ctx, setCtx] = useState<CtxState | null>(null);

  useEffect(() => {
    if (session.status !== "active") return;
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, [session.status]);

  const engineer = (session as any).engineer ?? session.user;

  return (
    <div
      onContextMenu={(e) => { e.preventDefault(); setCtx({ x: e.clientX, y: e.clientY }); }}
      className={cn(
        "rounded-[1rem] border p-4 transition-colors cursor-context-menu select-none",
        session.is_suspicious
          ? "border-orange-700/35 bg-orange-900/10"
          : session.status === "active"
            ? "border-musgo/30 bg-musgo/10"
            : "border-musgo/15 bg-carbon"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left */}
        <div className="flex items-start gap-3 min-w-0">
          <div className={cn(
            "w-2 h-2 rounded-full mt-1.5 shrink-0",
            session.status === "active" ? "bg-green-400 animate-pulse" : "bg-crema/20"
          )} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <span className="font-mono text-sm text-crema/90 font-medium">{session.server}</span>
              {session.is_suspicious && (
                <span className="flex items-center gap-1 font-mono text-[9px] px-2 py-0.5 rounded-full border border-orange-700/35 bg-orange-900/15 text-orange-400/80">
                  <AlertTriangle size={9} /> Sospechoso
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1">
              <div className="flex items-center gap-1.5">
                <User size={10} className="text-crema/25 shrink-0" />
                <span className="font-mono text-[10px] text-crema/50">{engineer}</span>
              </div>
              {session.client && (
                <div className="flex items-center gap-1.5">
                  <Server size={10} className="text-crema/25 shrink-0" />
                  <span className="font-mono text-[10px] text-crema/50">{session.client}</span>
                </div>
              )}
              {session.reason && (
                <div className="col-span-2 font-mono text-[10px] text-crema/35 truncate mt-0.5">
                  {session.reason}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right — times + button */}
        <div className="shrink-0 text-right space-y-1.5">
          <div className="flex items-center gap-1.5 justify-end">
            <Clock size={10} className="text-crema/25" />
            <span className="font-mono text-[10px] text-crema/45">
              Inicio: {formatTime(session.start)}
            </span>
          </div>

          {session.status === "closed" && session.end ? (
            <div className="flex items-center gap-1.5 justify-end">
              <Clock size={10} className="text-red-400/40" />
              <span className="font-mono text-[10px] text-red-400/60">
                Fin: {formatTime(session.end)}
              </span>
            </div>
          ) : null}

          {session.status === "closed" && (
            <div className="font-mono text-[10px] text-crema/30">
              Duración: {formatDuration(session.duration_min)}
            </div>
          )}

          {session.status === "active" && onTerminate && (
            <button
              onClick={onTerminate}
              className="mt-1 h-7 px-3 rounded-[0.5rem] bg-red-900/20 border border-red-700/35 font-mono text-[10px] text-red-400 hover:bg-red-900/30 transition-colors"
            >
              Terminado
            </button>
          )}
        </div>
      </div>

      {session.notes && (
        <p className="mt-2.5 pt-2.5 border-t border-musgo/15 font-mono text-[10px] text-crema/30">
          {session.notes}
        </p>
      )}

      {ctx && onDelete && (
        <ContextMenuPortal
          x={ctx.x} y={ctx.y}
          onClose={() => setCtx(null)}
          items={[
            {
              label:   "Eliminar registro",
              icon:    <Trash2 size={11} />,
              danger:  true,
              onClick: onDelete,
            },
          ]}
        />
      )}
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
type Tab = "active" | "history" | "alerts";

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AccessPage() {
  const [tab,         setTab]         = useState<Tab>("active");
  const [sessions,    setSessions]    = useState<AccessSession[]>([]);
  const [logs,        setLogs]        = useState<AccessSession[]>([]);
  const [alerts,      setAlerts]      = useState<AccessSession[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [showNew,     setShowNew]     = useState(false);
  const [closeTarget, setCloseTarget] = useState<AccessSession | null>(null);

  const loadActive = useCallback(async () => {
    setLoading(true);
    try { const r = await accessService.listSessions("active"); setSessions(r.sessions); }
    finally { setLoading(false); }
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try { const r = await accessService.getLogs(); setLogs(r.logs); }
    finally { setLoading(false); }
  }, []);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try { const r = await accessService.getAlerts(); setAlerts(r.alerts); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === "active")  loadActive();
    if (tab === "history") loadLogs();
    if (tab === "alerts")  loadAlerts();
  }, [tab, loadActive, loadLogs, loadAlerts]);

  function handleCreated(s: AccessSession) { setSessions((p) => [s, ...p]); }

  function handleClosed(updated: AccessSession) {
    setSessions((p) => p.filter((s) => s.id !== updated.id));
  }

  const TABS: { key: Tab; label: string; count?: number; icon: React.ElementType }[] = [
    { key: "active",  label: "Activas",   count: sessions.length, icon: Wifi       },
    { key: "history", label: "Historial", count: logs.length,     icon: Clock      },
    { key: "alerts",  label: "Alertas",   count: alerts.length,   icon: ShieldAlert },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] gap-4 min-h-0">
      {/* Header */}
      <div className="flex items-end justify-between shrink-0">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Módulo</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Acceso Remoto<span className="text-arcilla">.</span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              try {
                const blob = await accessService.downloadLog();
                const url  = URL.createObjectURL(blob);
                const a    = document.createElement("a");
                a.href     = url;
                a.download = `accesos_${new Date().toISOString().slice(0, 10)}.log`;
                a.click();
                URL.revokeObjectURL(url);
              } catch {}
            }}
            className="flex items-center gap-2 h-9 px-4 rounded-[0.75rem] border border-musgo/25 font-mono text-xs text-crema/40 hover:text-crema/70 hover:border-musgo/45 transition-colors"
          >
            <Download size={13} /> Descargar .log
          </button>
          <button
            onClick={() => setShowNew(true)}
            className="flex items-center gap-2 h-9 px-4 rounded-[0.75rem] bg-arcilla/10 border border-arcilla/35 font-mono text-xs text-arcilla/80 hover:bg-arcilla/15 transition-colors"
          >
            <Plus size={13} /> Nueva sesión
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 shrink-0 border-b border-musgo/20">
        {TABS.map(({ key, label, count, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 font-mono text-xs transition-all border-b-2 -mb-px",
              tab === key ? "text-crema/90 border-arcilla" : "text-crema/35 border-transparent hover:text-crema/60"
            )}>
            <Icon size={12} />
            {label}
            {count !== undefined && count > 0 && (
              <span className={cn(
                "flex items-center justify-center w-4 h-4 rounded-full text-[9px]",
                key === "alerts" ? "bg-orange-900/40 text-orange-400/80" :
                key === "active" ? "bg-green-900/30 text-green-400/70" : "bg-musgo/30 text-crema/40"
              )}>{count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 size={18} className="text-arcilla/40 animate-spin" />
          </div>
        ) : tab === "active" ? (
          sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Shield size={28} className="text-crema/15" />
              <p className="font-mono text-xs text-crema/25">Sin sesiones activas</p>
              <button onClick={() => setShowNew(true)}
                className="font-mono text-[10px] text-arcilla/60 hover:text-arcilla/90 underline transition-colors">
                Iniciar una sesión
              </button>
            </div>
          ) : (
            <div className="space-y-2 pr-1">
              {sessions.map((s) => (
                <SessionCard key={s.id} session={s} onTerminate={() => setCloseTarget(s)} />
              ))}
            </div>
          )
        ) : tab === "history" ? (
          logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-2">
              <Clock size={28} className="text-crema/15" />
              <p className="font-mono text-xs text-crema/25">Sin historial de sesiones</p>
            </div>
          ) : (
            <div className="space-y-2 pr-1">
              {logs.map((s) => (
                <SessionCard
                  key={s.id}
                  session={s}
                  onDelete={async () => {
                    await accessService.deleteSession(s.id);
                    setLogs((prev) => prev.filter((x) => x.id !== s.id));
                  }}
                />
              ))}
            </div>
          )
        ) : (
          alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-2">
              <ShieldAlert size={28} className="text-crema/15" />
              <p className="font-mono text-xs text-crema/25">Sin accesos sospechosos</p>
              <p className="font-mono text-[10px] text-crema/20 text-center max-w-xs">
                Se detectan sesiones fuera de horario (08:00–20:00) o mayores a 4 horas
              </p>
            </div>
          ) : (
            <div className="space-y-2 pr-1">
              {alerts.map((s) => <SessionCard key={s.id} session={s} />)}
            </div>
          )
        )}
      </div>

      {showNew && (
        <NewSessionModal onClose={() => setShowNew(false)} onCreated={handleCreated} />
      )}
      {closeTarget && (
        <TerminateModal
          session={closeTarget}
          onClose={() => setCloseTarget(null)}
          onClosed={handleClosed}
        />
      )}
    </div>
  );
}
