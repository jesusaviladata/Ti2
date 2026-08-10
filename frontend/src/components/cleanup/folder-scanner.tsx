"use client";

import { useState } from "react";
import { ScanLine, Loader2, Trash2, CheckSquare, Square, FolderOpen, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useScan, useCleanupFolders, useExecuteCleanup } from "@/hooks/useCleanup";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { ScannedFile } from "@/types/cleanup";

export function FolderScanner({ onAddFolder }: { onAddFolder: () => void }) {
  const [selectedFolder, setSelectedFolder] = useState<string | undefined>();
  const [scanEnabled,    setScanEnabled]    = useState(false);
  const [selected,       setSelected]       = useState<Set<string>>(new Set());

  const { data: folders } = useCleanupFolders();
  const { data: scan, isLoading: scanning, refetch } = useScan(selectedFolder, scanEnabled);
  const execute = useExecuteCleanup();

  const files = scan?.files ?? [];
  const allSelected = files.length > 0 && selected.size === files.length;

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(files.map((f) => f.path)));
  }

  function toggleFile(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  }

  async function handleCleanup() {
    if (!selected.size) return;
    await execute.mutateAsync({ paths: Array.from(selected) });
    setSelected(new Set());
    setScanEnabled(false);
  }

  function handleScan() {
    setScanEnabled(true);
    refetch();
  }

  if (!folders?.items.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-[0.75rem] bg-musgo/20 flex items-center justify-center mb-3">
          <FolderOpen size={20} className="text-crema/20" />
        </div>
        <p className="font-sans text-sm text-crema/40">Sin carpetas configuradas</p>
        <p className="font-mono text-xs text-crema/20 mt-1 mb-4">Añade una carpeta para empezar a escanear</p>
        <Button variant="outline" onClick={onAddFolder} className="text-xs gap-2">
          <FolderOpen size={13} /> Añadir carpeta
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedFolder ?? ""}
          onChange={(e) => { setSelectedFolder(e.target.value || undefined); setScanEnabled(false); }}
          className="h-9 bg-musgo/10 border border-musgo/30 rounded-[0.75rem] px-3 font-mono text-xs text-crema/70 focus:outline-none focus:border-arcilla/50 transition-colors"
        >
          <option value="">Todas las carpetas</option>
          {folders.items.map((f) => (
            <option key={f.id} value={f.id}>{f.label} — {f.path}</option>
          ))}
        </select>

        <Button onClick={handleScan} disabled={scanning} className="gap-2 text-xs h-9">
          {scanning
            ? <><Loader2 size={13} className="animate-spin" />Escaneando…</>
            : <><ScanLine size={13} />Escanear</>
          }
        </Button>

        {scan && (
          <Button variant="ghost" onClick={() => refetch()} className="h-9 px-2 text-crema/30 hover:text-crema">
            <RefreshCw size={13} />
          </Button>
        )}

        {selected.size > 0 && (
          <Button
            onClick={handleCleanup}
            disabled={execute.isPending}
            className="gap-2 text-xs h-9 bg-red-900/30 border border-red-800/40 text-red-300 hover:bg-red-900/50 ml-auto"
          >
            {execute.isPending
              ? <><Loader2 size={13} className="animate-spin" />Moviendo…</>
              : <><Trash2 size={13} />Mover a papelera ({selected.size})</>
            }
          </Button>
        )}
      </div>

      {/* Results summary */}
      {scan && (
        <div className="flex items-center gap-4 px-4 py-2.5 rounded-[0.75rem] bg-musgo/10 border border-musgo/20">
          <span className="font-mono text-xs text-crema/50">
            <span className="text-crema/80 font-medium">{scan.total}</span> archivo{scan.total !== 1 ? "s" : ""} candidatos
          </span>
          <span className="text-crema/20">·</span>
          <span className="font-mono text-xs text-crema/50">
            <span className="text-arcilla font-medium">{formatBytes(scan.totalBytes)}</span> recuperables
          </span>
          <span className="text-crema/20">·</span>
          <span className="font-mono text-[10px] text-crema/25">
            Escaneado {new Date(scan.scannedAt).toLocaleTimeString("es")}
          </span>
        </div>
      )}

      {/* File table */}
      {files.length > 0 && (
        <div className="rounded-[1rem] border border-musgo/20 overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-[32px_1fr_90px_100px_110px_80px] gap-2 px-4 py-2 text-[10px] font-mono text-crema/25 uppercase tracking-wider bg-musgo/10 border-b border-musgo/15">
            <button type="button" onClick={toggleAll} className="flex items-center justify-center">
              {allSelected
                ? <CheckSquare size={13} className="text-arcilla" />
                : <Square      size={13} className="text-crema/30" />
              }
            </button>
            <span>Nombre</span>
            <span>Tamaño</span>
            <span>Antigüedad</span>
            <span>Modificado</span>
            <span>Regla</span>
          </div>

          <div className="divide-y divide-musgo/10 max-h-96 overflow-y-auto">
            {files.map((file) => (
              <FileRow
                key={file.path}
                file={file}
                checked={selected.has(file.path)}
                onToggle={() => toggleFile(file.path)}
              />
            ))}
          </div>
        </div>
      )}

      {scan && files.length === 0 && (
        <div className="flex flex-col items-center py-12 text-center">
          <CheckSquare size={24} className="text-green-400/40 mb-2" />
          <p className="font-sans text-sm text-crema/40">Sin archivos para limpiar</p>
          <p className="font-mono text-xs text-crema/20 mt-1">Las reglas configuradas no encontraron candidatos</p>
        </div>
      )}

      {execute.isSuccess && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-[0.75rem] bg-green-900/10 border border-green-800/30 font-mono text-xs text-green-400">
          <CheckSquare size={13} />
          {execute.data.moved} archivos movidos a papelera · {formatBytes(execute.data.bytesFreed)} liberados
          {execute.data.errors.length > 0 && (
            <span className="text-red-400 ml-2">· {execute.data.errors.length} errores</span>
          )}
        </div>
      )}
    </div>
  );
}

function FileRow({
  file, checked, onToggle,
}: {
  file:     ScannedFile;
  checked:  boolean;
  onToggle: () => void;
}) {
  return (
    <div
      onClick={onToggle}
      className={cn(
        "grid grid-cols-[32px_1fr_90px_100px_110px_80px] gap-2 px-4 py-3 items-center cursor-pointer transition-colors",
        checked ? "bg-arcilla/5" : "hover:bg-musgo/5"
      )}
    >
      <div className="flex items-center justify-center">
        {checked
          ? <CheckSquare size={13} className="text-arcilla" />
          : <Square      size={13} className="text-crema/20" />
        }
      </div>

      <div className="min-w-0">
        <p className="font-sans text-xs text-crema/80 truncate">{file.name}</p>
        <p className="font-mono text-[10px] text-crema/25 truncate">{file.relativePath}</p>
      </div>

      <span className="font-mono text-xs text-crema/40">{formatBytes(file.sizeBytes)}</span>

      <span className={cn(
        "font-mono text-xs",
        file.ageDays > 90 ? "text-red-400/70" :
        file.ageDays > 30 ? "text-yellow-500/60" : "text-crema/35"
      )}>
        {file.ageDays < 1 ? "< 1 día" : `${Math.floor(file.ageDays)}d`}
      </span>

      <span className="font-mono text-[10px] text-crema/25">
        {new Date(file.modifiedAt).toLocaleDateString("es", { dateStyle: "short" })}
      </span>

      <span className="font-mono text-[10px] text-arcilla/60 truncate">{file.ruleName}</span>
    </div>
  );
}
