"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, KeyRound, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import { remoteCleanupService } from "@/services/remote-cleanup.service";
import type { CleanupServer } from "@/types/remote-cleanup";

const INPUT =
  "w-full h-9 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-3 font-mono text-xs text-crema/75 placeholder:text-crema/25 focus:outline-none focus:border-arcilla/40 transition-colors";

/**
 * Administración de servidores Core (solo admin): alta/baja de servidores SFTP/FTP,
 * rutas autorizadas (allowlist) y claves de host SSH conocidas (H-5). Antes vivía al
 * fondo de la página de Limpieza segura; ahora es una pestaña de Configuración.
 * Es autónomo: carga su propia lista de servidores y claves.
 */
export function CleanupServersAdmin() {
  const [servers, setServers] = useState<CleanupServer[]>([]);
  const [name, setName]   = useState("");
  const [host, setHost]   = useState("");
  const [port, setPort]   = useState(22);
  const [user, setUser]   = useState("");
  const [proto, setProto] = useState<"sftp" | "ftps" | "ftp">("sftp");
  const [base, setBase]   = useState("/");
  const [allow, setAllow] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr]     = useState<string | null>(null);
  const [hostKeys, setHostKeys] = useState<{ host: string; fingerprint: string }[]>([]);

  const loadServers = useCallback(async () => {
    try { setServers((await remoteCleanupService.listServers()).items); } catch {}
  }, []);
  const loadKeys = useCallback(async () => {
    try { setHostKeys((await remoteCleanupService.listHostKeys()).items); } catch {}
  }, []);
  useEffect(() => { loadServers(); loadKeys(); }, [loadServers, loadKeys]);

  async function forgetKey(hostPort: string) {
    const idx = hostPort.lastIndexOf(":");
    const h = hostPort.slice(0, idx);
    const p = Number(hostPort.slice(idx + 1)) || 22;
    await remoteCleanupService.forgetHostKey(h, p);
    loadKeys();
  }

  async function save() {
    setSaving(true); setErr(null);
    try {
      await remoteCleanupService.createServer({
        name, host, port, username: user, protocol: proto, rutaBase: base,
        allowlist: allow.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      setName(""); setHost(""); setUser(""); setAllow("");
      loadServers();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Error al guardar");
    } finally { setSaving(false); }
  }

  return (
    <div className="space-y-6">
      {/* Servidores existentes */}
      <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Server size={14} className="text-arcilla/70" />
          <span className="font-sans text-sm font-medium text-crema/75">Servidores Core</span>
          <span className="font-mono text-[10px] text-crema/30">({servers.length})</span>
        </div>
        {servers.length === 0 ? (
          <p className="font-mono text-xs text-crema/30 py-3">
            Aún no hay servidores. Configura uno abajo con sus rutas autorizadas.
          </p>
        ) : (
          <div className="space-y-1.5">
            {servers.map((s) => (
              <div key={s.id} className="flex items-center justify-between px-3 py-2 rounded-[0.5rem] bg-musgo/5 border border-musgo/15">
                <span className="font-mono text-[11px] text-crema/60">
                  {s.name} · {s.protocol}://{s.host}:{s.port} · {s.allowlist.length} ruta(s)
                </span>
                <button onClick={() => remoteCleanupService.deleteServer(s.id).then(loadServers)}
                  aria-label="Eliminar servidor"
                  className="text-crema/25 hover:text-red-400 transition-colors">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alta de servidor */}
      <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Plus size={14} className="text-arcilla/70" />
          <span className="font-sans text-sm font-medium text-crema/75">Agregar servidor y rutas autorizadas</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre (ej. Core Producción)" className={INPUT} />
          <div className="grid grid-cols-[1fr_90px] gap-2">
            <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Host / IP" className={INPUT} />
            <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} placeholder="Puerto" className={INPUT} />
          </div>
          <input value={user} onChange={(e) => setUser(e.target.value)} placeholder="Usuario" className={INPUT} />
          <select value={proto} onChange={(e) => setProto(e.target.value as any)} className={INPUT}>
            <option value="sftp">SFTP (recomendado)</option>
            <option value="ftps">FTPS</option>
            <option value="ftp">FTP (no recomendado)</option>
          </select>
          <input value={base} onChange={(e) => setBase(e.target.value)} placeholder="Ruta base (ej. /C:/BaseCore)" className={INPUT} />
          <div className="md:col-span-2">
            <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider block mb-1">
              Rutas autorizadas (una por línea) — sin esto, todo queda bloqueado
            </label>
            <textarea value={allow} onChange={(e) => setAllow(e.target.value)} rows={3}
              placeholder={"/C:/BaseCore/Logs\n/C:/BaseCore/Respuesta\n/C:/BaseCore/Logradian"}
              className={cn(INPUT, "h-auto py-2 resize-y")} />
          </div>
          {err && <p className="md:col-span-2 font-mono text-[11px] text-red-400/80">{err}</p>}
          <div className="md:col-span-2 flex justify-end">
            <button onClick={save} disabled={saving || !name.trim() || !host.trim()}
              className="h-9 px-5 rounded-[0.5rem] bg-arcilla/15 border border-arcilla/30 font-mono text-xs text-arcilla/90 hover:bg-arcilla/25 disabled:opacity-40 transition-colors">
              {saving ? "Guardando…" : "Guardar servidor"}
            </button>
          </div>
        </div>
      </div>

      {/* Claves de host SSH conocidas (H-5) */}
      <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
        <div className="flex items-center gap-2 mb-1.5">
          <KeyRound size={13} className="text-arcilla/70" />
          <span className="font-sans text-sm font-medium text-crema/75">Claves de host SSH conocidas</span>
        </div>
        <p className="font-mono text-[10px] text-crema/30 mb-3 leading-relaxed">
          Se fijan en la primera conexión. Si la clave de un host cambia, la conexión se bloquea (posible MITM).
          &ldquo;Olvidar&rdquo; re-autoriza el host en la próxima conexión.
        </p>
        {hostKeys.length === 0 ? (
          <p className="font-mono text-[10px] text-crema/25">Aún no hay claves fijadas.</p>
        ) : (
          <div className="space-y-1">
            {hostKeys.map((k) => (
              <div key={k.host} className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-[0.5rem] bg-musgo/5 border border-musgo/15">
                <span className="font-mono text-[10px] text-crema/60 truncate shrink-0">{k.host}</span>
                <span className="font-mono text-[9px] text-crema/25 truncate flex-1 text-right">SHA256:{k.fingerprint.slice(0, 20)}…</span>
                <button onClick={() => forgetKey(k.host)}
                  className="font-mono text-[9px] text-crema/40 hover:text-red-400 transition-colors shrink-0">Olvidar</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
