"use client";

import { useState, useCallback } from "react";
import {
  Folder, FileText, RefreshCw, ArrowUp, Trash2,
  FolderPlus, ChevronRight, Loader2, AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import { fmService } from "@/services/filemanager.service";
import type { FMConnection, FileEntry, FMOperation, StatusMessage } from "@/types/filemanager";

type ConnPayload = Pick<FMConnection, "host" | "port" | "protocol" | "username" | "password"> | null;

interface Props {
  side:       "local" | "remote";
  conn:       ConnPayload;
  onLog:      (msg: Omit<StatusMessage, "id" | "ts">) => void;
  onQueue:    (op: Omit<FMOperation, "id" | "ts">) => void;
  onOpDone:   (id: string, result: Partial<FMOperation>) => void;
}

export function FilePanel({ side, conn, onLog, onQueue, onOpDone }: Props) {
  const [path,     setPath]     = useState(side === "local" ? "C:\\" : "/");
  const [entries,  setEntries]  = useState<FileEntry[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loaded,   setLoaded]   = useState(false);

  const load = useCallback(async (p: string) => {
    setLoading(true);
    setError(null);
    setSelected(new Set());
    try {
      const res = await fmService.list(conn, p);
      setEntries(res.entries);
      setPath(res.path);
      setLoaded(true);
      onLog({ text: `Listando ${p} (${res.entries.length} elementos)`, kind: "info" });
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? "Error al listar";
      setError(msg);
      onLog({ text: msg, kind: "error" });
    } finally {
      setLoading(false);
    }
  }, [conn, onLog]);

  function navigateTo(entry: FileEntry) {
    if (!entry.isDir) return;
    const sep  = side === "local" ? "\\" : "/";
    const next = path.endsWith(sep) ? `${path}${entry.name}` : `${path}${sep}${entry.name}`;
    load(next);
  }

  function navigateUp() {
    if (side === "local") {
      const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
      if (parts.length <= 1) { load("C:\\"); return; }
      parts.pop();
      load(parts.join("\\") || "C:\\");
    } else {
      const parts = path.split("/").filter(Boolean);
      parts.pop();
      load("/" + parts.join("/") || "/");
    }
  }

  function toggleSelect(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function toggleAll() {
    setSelected(selected.size === entries.length ? new Set() : new Set(entries.map((e) => e.name)));
  }

  async function deleteSelected() {
    if (!selected.size) return;
    const names = Array.from(selected);
    const opId  = crypto.randomUUID();
    const label = names.length === 1 ? `Eliminar ${names[0]}` : `Eliminar ${names.length} elementos`;
    onQueue({ label, status: "running" });

    let deleted = 0;
    let errMsg  = "";
    for (const name of names) {
      const sep      = side === "local" ? "\\" : "/";
      const fullPath = path.endsWith(sep) ? `${path}${name}` : `${path}${sep}${name}`;
      const entry    = entries.find((e) => e.name === name);
      try {
        await fmService.delete(conn, fullPath, false);
        deleted++;
        onLog({ text: `Eliminado: ${fullPath}`, kind: "success" });
      } catch (e: any) {
        errMsg = e?.response?.data?.detail ?? e?.message ?? "Error";
        onLog({ text: `Error eliminando ${fullPath}: ${errMsg}`, kind: "error" });
      }
    }

    onOpDone(opId, {
      label,
      status:  errMsg ? "error" : "done",
      count:   deleted,
      error:   errMsg || undefined,
    });
    load(path);
  }

  async function deleteContents(entry: FileEntry) {
    if (!entry.isDir) return;
    const sep      = side === "local" ? "\\" : "/";
    const fullPath = path.endsWith(sep) ? `${path}${entry.name}` : `${path}${sep}${entry.name}`;
    const opId     = crypto.randomUUID();
    const label    = `Vaciar ${entry.name}`;
    onQueue({ label, status: "running" });
    try {
      const res = await fmService.delete(conn, fullPath, true);
      onOpDone(opId, { label, status: "done", count: res.deleted });
      onLog({ text: `Vaciada carpeta ${fullPath} (${res.deleted} elementos)`, kind: "success" });
      load(path);
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? "Error";
      onOpDone(opId, { label, status: "error", error: msg });
      onLog({ text: `Error vaciando ${fullPath}: ${msg}`, kind: "error" });
    }
  }

  const isConnected = side === "remote" ? !!conn : true;

  return (
    <div className="flex flex-col h-full min-h-0 border border-musgo/20 rounded-[1rem] overflow-hidden bg-carbon">
      {/* Panel header */}
      <div className="flex items-center gap-1.5 px-3 py-2 bg-musgo/10 border-b border-musgo/20 shrink-0">
        <span className="font-mono text-[10px] text-crema/30 uppercase tracking-widest mr-1">
          {side === "local" ? "Local" : "Remoto"}
        </span>
        <div className="flex-1 flex items-center gap-1 bg-carbon/60 border border-musgo/20 rounded-[0.5rem] px-2 py-1 min-w-0">
          <span className="font-mono text-[10px] text-crema/50 truncate">{path}</span>
        </div>
        <button onClick={navigateUp} disabled={!loaded || loading}
          className="w-6 h-6 flex items-center justify-center rounded text-crema/30 hover:text-crema/70 disabled:opacity-30 transition-colors">
          <ArrowUp size={12} />
        </button>
        <button onClick={() => load(path)} disabled={loading}
          className="w-6 h-6 flex items-center justify-center rounded text-crema/30 hover:text-crema/70 disabled:opacity-30 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Action bar */}
      {loaded && (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-musgo/15 shrink-0">
          <button
            onClick={deleteSelected}
            disabled={!selected.size}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-[0.5rem] font-mono text-[10px] bg-red-900/15 border border-red-800/25 text-red-400/70 hover:text-red-400 disabled:opacity-30 transition-colors"
          >
            <Trash2 size={10} /> Eliminar{selected.size > 0 ? ` (${selected.size})` : ""}
          </button>
          <span className="flex-1" />
          {selected.size > 0 && (
            <span className="font-mono text-[10px] text-crema/25">
              {selected.size} seleccionado{selected.size !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {!isConnected && !loaded ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-center p-6">
            <span className="font-mono text-xs text-crema/20">Sin conexión remota</span>
            <span className="font-mono text-[10px] text-crema/15">Conecta un servidor en la barra superior</span>
          </div>
        ) : !loaded ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <button
              onClick={() => load(path)}
              className="px-4 py-2 rounded-[0.75rem] bg-musgo/20 border border-musgo/30 font-mono text-xs text-crema/50 hover:text-crema/80 hover:border-musgo/50 transition-colors"
            >
              {side === "local" ? "Explorar servidor" : "Explorar remoto"}
            </button>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 p-6 text-center">
            <AlertCircle size={18} className="text-red-400/60" />
            <span className="font-mono text-xs text-red-400/70">{error}</span>
            <button onClick={() => load(path)} className="font-mono text-[10px] text-crema/30 hover:text-crema/60 underline">
              Reintentar
            </button>
          </div>
        ) : entries.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <span className="font-mono text-xs text-crema/20">Carpeta vacía</span>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-musgo/15 sticky top-0 bg-carbon">
                <th className="w-8 px-3 py-2">
                  <input type="checkbox" checked={selected.size === entries.length && entries.length > 0}
                    onChange={toggleAll}
                    className="w-3 h-3 accent-arcilla rounded cursor-pointer" />
                </th>
                <th className="font-mono text-[9px] text-crema/25 uppercase tracking-wider py-2 pr-2">Nombre</th>
                <th className="font-mono text-[9px] text-crema/25 uppercase tracking-wider py-2 pr-2 text-right w-20">Tamaño</th>
                <th className="font-mono text-[9px] text-crema/25 uppercase tracking-wider py-2 pr-3 text-right w-28 hidden md:table-cell">Modificado</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr
                  key={entry.name}
                  className={cn(
                    "group border-b border-musgo/8 transition-colors cursor-pointer",
                    selected.has(entry.name) ? "bg-arcilla/8" : "hover:bg-musgo/8"
                  )}
                  onClick={() => toggleSelect(entry.name)}
                  onDoubleClick={() => navigateTo(entry)}
                >
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(entry.name)}
                      onChange={() => toggleSelect(entry.name)}
                      className="w-3 h-3 accent-arcilla rounded cursor-pointer" />
                  </td>
                  <td className="py-2 pr-2">
                    <div className="flex items-center gap-2">
                      {entry.isDir
                        ? <Folder size={13} className="text-arcilla/60 shrink-0" />
                        : <FileText size={13} className="text-crema/30 shrink-0" />
                      }
                      <span className="font-mono text-xs text-crema/75 truncate">{entry.name}</span>
                      {entry.isDir && <ChevronRight size={10} className="text-crema/20 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />}
                    </div>
                  </td>
                  <td className="py-2 pr-2 text-right font-mono text-[10px] text-crema/35 tabular-nums">
                    {entry.isDir ? "—" : formatBytes(entry.size)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-[10px] text-crema/25 hidden md:table-cell">
                    {entry.modified ? new Date(entry.modified * 1000).toLocaleDateString("es", { dateStyle: "short" }) : "—"}
                  </td>
                  <td className="pr-2" onClick={(e) => e.stopPropagation()}>
                    {entry.isDir && (
                      <button
                        onClick={() => deleteContents(entry)}
                        title="Vaciar carpeta"
                        className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded text-crema/25 hover:text-red-400 transition-all"
                      >
                        <Trash2 size={10} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      {loaded && (
        <div className="px-3 py-1.5 border-t border-musgo/15 shrink-0">
          <span className="font-mono text-[10px] text-crema/20">
            {entries.length} elemento{entries.length !== 1 ? "s" : ""}
          </span>
        </div>
      )}
    </div>
  );
}
