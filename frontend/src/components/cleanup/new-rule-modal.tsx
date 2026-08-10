"use client";

import { useState } from "react";
import { X, Tag, Plus, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCreateRule, useCleanupFolders } from "@/hooks/useCleanup";
import { cn } from "@/lib/utils";
import type { KeepPolicy } from "@/types/cleanup";

interface Props { open: boolean; onClose: () => void }

const KEEP_OPTIONS: { value: KeepPolicy; label: string; desc: string }[] = [
  { value: "latest",   label: "Solo el más reciente", desc: "Conserva el archivo más nuevo, elimina el resto" },
  { value: "latest_n", label: "Últimos N",             desc: "Conserva los N archivos más recientes" },
  { value: "none",     label: "Eliminar todos",        desc: "Elimina todos los archivos que coincidan" },
  { value: "all",      label: "Solo auditar",          desc: "Lista candidatos sin eliminar nada" },
];

const PRESET_PATTERNS = ["*BCK*", "*backup*", "*BACKUP*", "*.bak", "*.tmp", "*_old*"];

export function NewRuleModal({ open, onClose }: Props) {
  const { data: foldersData } = useCleanupFolders();
  const createRule = useCreateRule();

  const [name,       setName]       = useState("");
  const [folderId,   setFolderId]   = useState("");
  const [patterns,   setPatterns]   = useState<string[]>(["*BCK*"]);
  const [extensions, setExtensions] = useState<string[]>([]);
  const [keep,       setKeep]       = useState<KeepPolicy>("latest");
  const [keepN,      setKeepN]      = useState(3);
  const [minAge,     setMinAge]     = useState(0);
  const [patInput,   setPatInput]   = useState("");
  const [extInput,   setExtInput]   = useState("");

  if (!open) return null;

  function addPattern() {
    const v = patInput.trim();
    if (v && !patterns.includes(v)) setPatterns([...patterns, v]);
    setPatInput("");
  }

  function addExtension() {
    const v = extInput.trim().startsWith(".") ? extInput.trim() : `.${extInput.trim()}`;
    if (extInput.trim() && !extensions.includes(v)) setExtensions([...extensions, v]);
    setExtInput("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !patterns.length) return;
    await createRule.mutateAsync({
      name,
      folderId:   folderId || null,
      patterns,
      extensions,
      keep,
      keepN,
      minAgeDays: minAge,
      enabled:    true,
    } as any);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative z-10 w-full max-w-lg rounded-[1.5rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-musgo/20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[0.65rem] bg-musgo/30 flex items-center justify-center">
              <Tag size={15} className="text-crema/60" />
            </div>
            <div>
              <p className="font-mono text-xs text-arcilla uppercase tracking-widest mb-0.5">Limpieza</p>
              <h2 className="font-display text-xl italic font-light text-crema">
                Nueva regla BCK<span className="text-arcilla">.</span>
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="text-crema/30 hover:text-crema"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto">
          {/* Name */}
          <Field label="Nombre de la regla *">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Backups RAR semanales"
              required
              className={INPUT_CLS}
            />
          </Field>

          {/* Folder */}
          <Field label="Aplicar a carpeta">
            <select value={folderId} onChange={(e) => setFolderId(e.target.value)} className={INPUT_CLS}>
              <option value="">Todas las carpetas configuradas</option>
              {foldersData?.items.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          </Field>

          {/* Patterns */}
          <Field label="Patrones de nombre (glob)">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {PRESET_PATTERNS.map((p) => (
                <button
                  key={p} type="button"
                  onClick={() => !patterns.includes(p) && setPatterns([...patterns, p])}
                  className={cn(
                    "px-2.5 py-0.5 rounded-md font-mono text-[10px] border transition-colors",
                    patterns.includes(p)
                      ? "bg-arcilla/15 border-arcilla/35 text-arcilla/80"
                      : "bg-musgo/10 border-musgo/25 text-crema/40 hover:border-musgo/45"
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={patInput}
                onChange={(e) => setPatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addPattern())}
                placeholder="Patrón personalizado…"
                className={cn(INPUT_CLS, "flex-1")}
              />
              <button type="button" onClick={addPattern}
                className="w-9 h-9 rounded-[0.625rem] bg-musgo/20 border border-musgo/30 text-crema/40 hover:text-crema flex items-center justify-center">
                <Plus size={13} />
              </button>
            </div>
            {patterns.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {patterns.map((p) => (
                  <span key={p} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-arcilla/10 border border-arcilla/25 font-mono text-[10px] text-arcilla/70">
                    {p}
                    <button type="button" onClick={() => setPatterns(patterns.filter((x) => x !== p))} className="text-arcilla/40 hover:text-arcilla ml-0.5">×</button>
                  </span>
                ))}
              </div>
            )}
          </Field>

          {/* Extensions */}
          <Field label="Extensiones (opcional)">
            <div className="flex gap-2">
              <input
                value={extInput}
                onChange={(e) => setExtInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addExtension())}
                placeholder=".rar  .bak  .zip"
                className={cn(INPUT_CLS, "flex-1")}
              />
              <button type="button" onClick={addExtension}
                className="w-9 h-9 rounded-[0.625rem] bg-musgo/20 border border-musgo/30 text-crema/40 hover:text-crema flex items-center justify-center">
                <Plus size={13} />
              </button>
            </div>
            {extensions.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {extensions.map((e) => (
                  <span key={e} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-musgo/20 border border-musgo/30 font-mono text-[10px] text-crema/50">
                    {e}
                    <button type="button" onClick={() => setExtensions(extensions.filter((x) => x !== e))} className="text-crema/30 hover:text-crema ml-0.5">×</button>
                  </span>
                ))}
              </div>
            )}
          </Field>

          {/* Keep policy */}
          <Field label="Política de conservación">
            <div className="grid grid-cols-2 gap-2">
              {KEEP_OPTIONS.map(({ value, label, desc }) => (
                <button
                  key={value} type="button"
                  onClick={() => setKeep(value)}
                  className={cn(
                    "p-3 rounded-[0.75rem] border text-left transition-all duration-150",
                    keep === value
                      ? "bg-arcilla/10 border-arcilla/40 text-crema"
                      : "bg-musgo/10 border-musgo/20 text-crema/50 hover:border-musgo/40"
                  )}
                >
                  <p className="font-sans text-xs font-medium">{label}</p>
                  <p className="font-mono text-[10px] mt-0.5 opacity-60 leading-tight">{desc}</p>
                </button>
              ))}
            </div>
            {keep === "latest_n" && (
              <div className="mt-2 flex items-center gap-3">
                <label className="font-mono text-[10px] text-crema/35">Conservar últimos:</label>
                <input
                  type="number" min={1} max={100}
                  value={keepN}
                  onChange={(e) => setKeepN(+e.target.value)}
                  className="w-20 h-8 bg-musgo/10 border border-musgo/30 rounded-[0.5rem] px-3 font-mono text-xs text-crema/70 focus:outline-none focus:border-arcilla/50"
                />
              </div>
            )}
          </Field>

          {/* Min age */}
          <Field label="Edad mínima para eliminar">
            <div className="flex items-center gap-3">
              <input
                type="number" min={0} max={365}
                value={minAge}
                onChange={(e) => setMinAge(+e.target.value)}
                className="w-20 h-9 bg-musgo/10 border border-musgo/30 rounded-[0.75rem] px-3 font-mono text-xs text-crema/70 focus:outline-none focus:border-arcilla/50"
              />
              <span className="font-mono text-xs text-crema/35">días (0 = sin restricción)</span>
            </div>
          </Field>

          <div className="flex gap-3 pt-1 border-t border-musgo/15">
            <Button variant="outline" type="button" onClick={onClose} className="flex-1">Cancelar</Button>
            <Button type="submit" className="flex-1" disabled={!name.trim() || !patterns.length || createRule.isPending}>
              {createRule.isPending
                ? <><Loader2 size={13} className="animate-spin mr-2" />Creando…</>
                : <><Tag size={13} className="mr-2" />Crear regla</>
              }
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

const INPUT_CLS = "w-full h-9 bg-musgo/10 border border-musgo/30 rounded-[0.75rem] px-3 font-mono text-xs text-crema/75 placeholder-crema/20 focus:outline-none focus:border-arcilla/50 transition-colors";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="font-mono text-[10px] text-crema/40 uppercase tracking-wider">{label}</p>
      {children}
    </div>
  );
}
