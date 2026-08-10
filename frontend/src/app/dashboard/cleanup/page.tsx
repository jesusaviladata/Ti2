"use client";

import { useState, useRef, useCallback } from "react";
import {
  Wifi, WifiOff, Loader2, ChevronDown, Trash2, Eye, EyeOff,
  CheckCircle2, XCircle, Clock, Server, Zap, KeyRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilePanel } from "@/components/filemanager/file-panel";
import { QuickCleanupPanel } from "@/components/filemanager/quick-cleanup-panel";
import { fmService } from "@/services/filemanager.service";
import { useFMStore } from "@/store/fm-connections.store";
import { cn } from "@/lib/utils";
import type { FMConnection, FMProtocol, StatusMessage, FMOperation } from "@/types/filemanager";

// ── Status log ────────────────────────────────────────────────────────────────
function StatusLog({ messages }: { messages: StatusMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  return (
    <div className="h-[80px] overflow-y-auto font-mono text-[10px] bg-black/30 border border-musgo/20 rounded-[0.75rem] px-3 py-2 space-y-0.5">
      {messages.length === 0 && (
        <span className="text-crema/15">Esperando actividad…</span>
      )}
      {messages.map((m) => (
        <div key={m.id} className={cn(
          "flex gap-2 leading-relaxed",
          m.kind === "error"   ? "text-red-400/80" :
          m.kind === "success" ? "text-green-400/70" :
          "text-crema/35"
        )}>
          <span className="text-crema/20 shrink-0">
            {m.ts.toLocaleTimeString("es", { timeStyle: "medium" })}
          </span>
          <span>{m.text}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

// ── Operation queue ───────────────────────────────────────────────────────────
function OperationQueue({ ops }: { ops: FMOperation[] }) {
  if (!ops.length) return null;
  return (
    <div className="border border-musgo/20 rounded-[0.875rem] overflow-hidden shrink-0">
      <div className="px-3 py-1.5 bg-musgo/10 border-b border-musgo/15">
        <span className="font-mono text-[10px] text-crema/30 uppercase tracking-widest">Cola de operaciones</span>
      </div>
      <div className="divide-y divide-musgo/10 max-h-32 overflow-y-auto">
        {[...ops].reverse().map((op) => (
          <div key={op.id} className="flex items-center gap-3 px-3 py-2">
            {op.status === "running" && <Loader2 size={11} className="text-arcilla/70 animate-spin shrink-0" />}
            {op.status === "done"    && <CheckCircle2 size={11} className="text-green-400 shrink-0" />}
            {op.status === "error"   && <XCircle size={11} className="text-red-400 shrink-0" />}
            {op.status === "pending" && <Clock size={11} className="text-crema/25 shrink-0" />}
            <span className="font-mono text-xs text-crema/60 flex-1 truncate">{op.label}</span>
            {op.count !== undefined && op.status === "done" && (
              <span className="font-mono text-[10px] text-crema/30">{op.count} elem.</span>
            )}
            {op.error && (
              <span className="font-mono text-[10px] text-red-400/60 truncate max-w-[200px]">{op.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Connection bar ────────────────────────────────────────────────────────────
const PROTOCOLS: { value: FMProtocol; label: string; defaultPort: number }[] = [
  { value: "sftp",  label: "SFTP",  defaultPort: 22  },
  { value: "ftp",   label: "FTP",   defaultPort: 21  },
  { value: "ftps",  label: "FTPS",  defaultPort: 990 },
];

interface ConnectionBarProps {
  onConnect:    (conn: FMConnection) => void;
  onDisconnect: () => void;
  connected:    boolean;
  connecting:   boolean;
  activeConn:   FMConnection | null;
}

function ConnectionBar({ onConnect, onDisconnect, connected, connecting, activeConn }: ConnectionBarProps) {
  const { connections, addConnection, removeConnection, setActive } = useFMStore();
  const [host,     setHost]     = useState("");
  const [user,     setUser]     = useState("");
  const [pass,     setPass]     = useState("");
  const [port,     setPort]     = useState(22);
  const [proto,    setProto]    = useState<FMProtocol>("sftp");
  const [label,    setLabel]    = useState("");
  const [showPw,   setShowPw]   = useState(false);
  const [showSave, setShowSave] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  // Llave privada .pem (AWS EC2, solo SFTP) — solo en memoria, nunca se persiste
  const [usePem,  setUsePem]  = useState(false);
  const [pemKey,  setPemKey]  = useState("");
  const [pemName, setPemName] = useState("");

  function handleProto(p: FMProtocol) {
    setProto(p);
    setPort(PROTOCOLS.find((x) => x.value === p)?.defaultPort ?? 22);
    if (p !== "sftp") setUsePem(false);   // la llave .pem solo aplica a SFTP
  }

  function onPemFile(file: File | null) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { setPemKey(String(reader.result ?? "")); setPemName(file.name); };
    reader.readAsText(file);
  }

  function fill(c: FMConnection) {
    setHost(c.host); setUser(c.username); setPass(c.password);
    setPort(c.port); setProto(c.protocol); setLabel(c.label);
    setUsePem(false); setPemKey(""); setPemName("");
    setShowSaved(false);
  }

  function handleConnect() {
    const privateKey = usePem ? pemKey : "";
    const conn: FMConnection = {
      id: crypto.randomUUID(), label: label || host,
      host, port, protocol: proto, username: user, password: pass, privateKey,
      createdAt: new Date().toISOString(),
    };
    if (showSave && label.trim()) {
      addConnection({ label: label || host, host, port, protocol: proto, username: user, password: pass, privateKey });
    }
    onConnect(conn);
  }

  const INPUT = "h-8 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-2.5 font-mono text-xs text-crema/75 placeholder:text-crema/20 focus:outline-none focus:border-arcilla/40 transition-colors";

  return (
    <div className="rounded-[1rem] border border-musgo/20 bg-carbon p-3 space-y-2 shrink-0">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Saved connections dropdown */}
        <div className="relative">
          <button onClick={() => setShowSaved((v) => !v)}
            className="h-8 px-3 flex items-center gap-1.5 bg-musgo/15 border border-musgo/25 rounded-[0.5rem] font-mono text-[10px] text-crema/50 hover:border-musgo/45 transition-colors">
            <Server size={11} />
            Guardadas
            <ChevronDown size={10} className={cn("transition-transform", showSaved && "rotate-180")} />
          </button>
          {showSaved && (
            <div className="absolute left-0 top-full mt-1 z-50 w-64 rounded-[0.75rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
              {connections.length === 0 ? (
                <p className="font-mono text-[10px] text-crema/25 px-4 py-3">Sin conexiones guardadas</p>
              ) : (
                <div className="py-1 max-h-48 overflow-y-auto">
                  {connections.map((c) => (
                    <div key={c.id} className="flex items-center gap-2 px-3 py-2 hover:bg-musgo/10 group">
                      <button onClick={() => fill(c)} className="flex-1 text-left">
                        <p className="font-mono text-xs text-crema/70">{c.label}</p>
                        <p className="font-mono text-[9px] text-crema/30">{c.protocol.toUpperCase()} · {c.host}:{c.port}</p>
                      </button>
                      <button onClick={() => removeConnection(c.id)}
                        className="opacity-0 group-hover:opacity-100 text-crema/20 hover:text-red-400 transition-all">
                        <XCircle size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Protocol selector */}
        <div className="flex rounded-[0.5rem] border border-musgo/25 overflow-hidden">
          {PROTOCOLS.map((p) => (
            <button key={p.value} onClick={() => handleProto(p.value)}
              className={cn("h-8 px-2.5 font-mono text-[10px] transition-colors",
                proto === p.value ? "bg-arcilla/15 text-arcilla/80" : "text-crema/35 hover:text-crema/55")}>
              {p.label}
            </button>
          ))}
        </div>

        {/* Host */}
        <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Host / IP"
          className={cn(INPUT, "w-40")} />
        {/* Port */}
        <input value={port} onChange={(e) => setPort(+e.target.value)} type="number"
          className={cn(INPUT, "w-16")} />
        {/* User */}
        <input value={user} onChange={(e) => setUser(e.target.value)} placeholder="Usuario"
          className={cn(INPUT, "w-28")} />
        {/* Password o llave .pem */}
        {usePem ? (
          <label className={cn(INPUT, "w-40 flex items-center gap-1.5 cursor-pointer hover:border-arcilla/40 overflow-hidden")}>
            <KeyRound size={11} className="text-arcilla/60 shrink-0" />
            <span className={cn("truncate", pemName ? "text-crema/75" : "text-crema/25")}>
              {pemName || "Archivo .pem…"}
            </span>
            <input type="file" className="hidden" onChange={(e) => onPemFile(e.target.files?.[0] ?? null)} />
          </label>
        ) : (
          <div className="relative">
            <input value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Contraseña"
              type={showPw ? "text" : "password"} className={cn(INPUT, "w-28 pr-7")} />
            <button onClick={() => setShowPw((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-crema/25 hover:text-crema/55 transition-colors">
              {showPw ? <EyeOff size={11} /> : <Eye size={11} />}
            </button>
          </div>
        )}
        {proto === "sftp" && (
          <button onClick={() => setUsePem((v) => !v)}
            title={usePem ? "Usar contraseña" : "Usar llave privada .pem (AWS EC2)"}
            className={cn("h-8 px-2.5 rounded-[0.5rem] border font-mono text-[10px] transition-colors flex items-center gap-1",
              usePem ? "bg-arcilla/10 border-arcilla/30 text-arcilla/70" : "border-musgo/25 text-crema/30 hover:text-crema/55")}>
            <KeyRound size={10} /> .pem
          </button>
        )}

        {/* Label + save toggle */}
        <button onClick={() => setShowSave((v) => !v)}
          className={cn("h-8 px-2.5 rounded-[0.5rem] border font-mono text-[10px] transition-colors",
            showSave ? "bg-arcilla/10 border-arcilla/30 text-arcilla/70" : "border-musgo/25 text-crema/30 hover:text-crema/55")}>
          Guardar
        </button>
        {showSave && (
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Etiqueta"
            className={cn(INPUT, "w-28")} />
        )}

        {/* Connect / Disconnect */}
        {connected ? (
          <button onClick={onDisconnect}
            className="h-8 px-3 flex items-center gap-1.5 rounded-[0.5rem] bg-red-900/15 border border-red-800/25 font-mono text-[10px] text-red-400/70 hover:text-red-400 transition-colors">
            <WifiOff size={11} /> Desconectar
          </button>
        ) : (
          <button onClick={handleConnect} disabled={!host.trim() || connecting}
            className="h-8 px-3 flex items-center gap-1.5 rounded-[0.5rem] bg-arcilla/10 border border-arcilla/30 font-mono text-[10px] text-arcilla/80 hover:bg-arcilla/15 disabled:opacity-40 transition-colors">
            {connecting
              ? <><Loader2 size={11} className="animate-spin" /> Conectando…</>
              : <><Wifi size={11} /> Conectar</>
            }
          </button>
        )}
      </div>

      {/* Connected badge */}
      {connected && activeConn && (
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
          <span className="font-mono text-[10px] text-green-400/70">
            Conectado a {activeConn.protocol.toUpperCase()} · {activeConn.host}:{activeConn.port} · {activeConn.username}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function FileManagerPage() {
  const { toPayload } = useFMStore();
  const [activeConn,  setActiveConn]  = useState<FMConnection | null>(null);
  const [connecting,  setConnecting]  = useState(false);
  const [messages,    setMessages]    = useState<StatusMessage[]>([]);
  const [operations,  setOperations]  = useState<FMOperation[]>([]);
  const [remotePath,  setRemotePath]  = useState("/");

  const addLog = useCallback((msg: Omit<StatusMessage, "id" | "ts">) => {
    setMessages((prev) => [...prev.slice(-49), { ...msg, id: crypto.randomUUID(), ts: new Date() }]);
  }, []);

  const addOp = useCallback((op: Omit<FMOperation, "id" | "ts">) => {
    const id = crypto.randomUUID();
    setOperations((prev) => [...prev, { ...op, id, ts: new Date() }]);
    return id;
  }, []);

  const updateOp = useCallback((id: string, result: Partial<FMOperation>) => {
    setOperations((prev) => prev.map((o) => o.id === id ? { ...o, ...result } : o));
  }, []);

  // Queue proxy that returns the op id
  function queueProxy(op: Omit<FMOperation, "id" | "ts">) { addOp(op); }

  async function handleConnect(conn: FMConnection) {
    setConnecting(true);
    addLog({ text: `Conectando a ${conn.protocol.toUpperCase()} ${conn.host}:${conn.port}…`, kind: "info" });
    try {
      const payload = toPayload(conn);
      const res = await fmService.test(payload);
      if (res.connected) {
        setActiveConn(conn);
        addLog({ text: `Conexión establecida. Usuario: ${conn.username}`, kind: "success" });
      } else {
        addLog({ text: `Error de conexión: ${res.error ?? "sin detalles"}`, kind: "error" });
      }
    } catch (e: any) {
      addLog({ text: `Error: ${e?.response?.data?.detail ?? e?.message}`, kind: "error" });
    } finally {
      setConnecting(false);
    }
  }

  function handleDisconnect() {
    addLog({ text: `Desconectado de ${activeConn?.host}`, kind: "info" });
    setActiveConn(null);
  }

  const remotePayload = activeConn ? toPayload(activeConn) : null;

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] gap-3 min-h-0">
      {/* Page header */}
      <div className="flex items-end justify-between shrink-0">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Módulo</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Gestor de Archivos<span className="text-arcilla">.</span>
          </h1>
        </div>
      </div>

      {/* Connection bar */}
      <ConnectionBar
        onConnect={handleConnect}
        onDisconnect={handleDisconnect}
        connected={!!activeConn}
        connecting={connecting}
        activeConn={activeConn}
      />

      {/* Status log */}
      <StatusLog messages={messages} />

      {/* Main panels */}
      <div className="flex-1 grid grid-cols-[1fr_1fr_220px] gap-3 min-h-0 overflow-hidden">
        <FilePanel
          side="local"
          conn={null}
          onLog={addLog}
          onQueue={queueProxy}
          onOpDone={updateOp}
        />
        <FilePanel
          side="remote"
          conn={remotePayload}
          onLog={addLog}
          onQueue={queueProxy}
          onOpDone={updateOp}
        />
        <QuickCleanupPanel
          conn={remotePayload}
          basePath={remotePath}
          onLog={addLog}
          onQueue={queueProxy}
          onOpDone={updateOp}
        />
      </div>

      {/* Operation queue */}
      <OperationQueue ops={operations} />
    </div>
  );
}
