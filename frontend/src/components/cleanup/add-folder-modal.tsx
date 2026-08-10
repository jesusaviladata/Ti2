"use client";

import { useState } from "react";
import { X, FolderOpen, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAddFolder } from "@/hooks/useCleanup";

interface Props { open: boolean; onClose: () => void }

const QUICK_PATHS = [
  { label: "Backups locales",  path: "C:\\Backups" },
  { label: "Archivos temp",    path: "C:\\Windows\\Temp" },
  { label: "Downloads",        path: "C:\\Users\\Public\\Downloads" },
];

export function AddFolderModal({ open, onClose }: Props) {
  const [path,  setPath]  = useState("");
  const [label, setLabel] = useState("");
  const addFolder = useAddFolder();

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!path.trim()) return;
    await addFolder.mutateAsync({ path: path.trim(), label: label.trim() || undefined });
    setPath(""); setLabel("");
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative z-10 w-full max-w-md rounded-[1.5rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-5 border-b border-musgo/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[0.65rem] bg-musgo/30 flex items-center justify-center">
              <FolderOpen size={15} className="text-crema/60" />
            </div>
            <div>
              <p className="font-mono text-xs text-arcilla uppercase tracking-widest mb-0.5">Limpieza</p>
              <h2 className="font-display text-xl italic font-light text-crema">
                Añadir carpeta<span className="text-arcilla">.</span>
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="text-crema/30 hover:text-crema transition-colors">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Quick paths */}
          <div>
            <p className="font-mono text-[10px] text-crema/30 uppercase tracking-wider mb-2">Rutas frecuentes</p>
            <div className="flex flex-wrap gap-2">
              {QUICK_PATHS.map(({ label: l, path: p }) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => { setPath(p); setLabel(l); }}
                  className="px-3 py-1 rounded-[0.5rem] bg-musgo/15 border border-musgo/25 font-mono text-[10px] text-crema/45 hover:border-musgo/50 hover:text-crema/65 transition-colors"
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          {/* Path input */}
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider">
              Ruta de la carpeta *
            </label>
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="C:\Ruta\a\la\carpeta"
              required
              className="w-full h-10 bg-musgo/10 border border-musgo/30 rounded-[0.75rem] px-4 font-mono text-sm text-crema/75 placeholder-crema/20 focus:outline-none focus:border-arcilla/50 transition-colors"
            />
          </div>

          {/* Label input */}
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] text-crema/40 uppercase tracking-wider">
              Etiqueta (opcional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Nombre descriptivo"
              className="w-full h-10 bg-musgo/10 border border-musgo/30 rounded-[0.75rem] px-4 font-mono text-sm text-crema/75 placeholder-crema/20 focus:outline-none focus:border-arcilla/50 transition-colors"
            />
          </div>

          {addFolder.isError && (
            <p className="font-mono text-xs text-red-400 bg-red-900/10 border border-red-800/20 rounded-[0.75rem] px-4 py-3">
              Error al añadir carpeta
            </p>
          )}

          <div className="flex gap-3 pt-1">
            <Button variant="outline" type="button" onClick={onClose} className="flex-1">Cancelar</Button>
            <Button type="submit" className="flex-1" disabled={!path.trim() || addFolder.isPending}>
              {addFolder.isPending
                ? <><Loader2 size={13} className="animate-spin mr-2" />Añadiendo…</>
                : <><FolderOpen size={13} className="mr-2" />Añadir carpeta</>
              }
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
