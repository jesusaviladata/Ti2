"use client";

import { useState } from "react";
import { Zap, Trash2, Plus, X, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { fmService } from "@/services/filemanager.service";
import { useFMStore } from "@/store/fm-connections.store";
import type { FMConnection, QuickRule, StatusMessage, FMOperation } from "@/types/filemanager";

type ConnPayload = Pick<FMConnection, "host" | "port" | "protocol" | "username" | "password"> | null;

interface Props {
  conn:     ConnPayload;
  basePath: string;
  onLog:    (msg: Omit<StatusMessage, "id" | "ts">) => void;
  onQueue:  (op: Omit<FMOperation, "id" | "ts">) => void;
  onOpDone: (id: string, result: Partial<FMOperation>) => void;
}

type RuleState = "idle" | "running" | "done" | "error";

export function QuickCleanupPanel({ conn, basePath, onLog, onQueue, onOpDone }: Props) {
  const { quickRules, addQuickRule, removeQuickRule } = useFMStore();
  const [states, setStates] = useState<Record<string, RuleState>>({});
  const [adding, setAdding] = useState(false);
  const [newLabel,   setNewLabel]   = useState("");
  const [newPath,    setNewPath]    = useState("");
  const [newType,    setNewType]    = useState<"contents" | "pattern">("contents");
  const [newPattern, setNewPattern] = useState("");

  function setRuleState(id: string, state: RuleState) {
    setStates((prev) => ({ ...prev, [id]: state }));
  }

  async function runRule(rule: QuickRule) {
    if (!conn) {
      onLog({ text: "Sin conexión remota activa", kind: "error" });
      return;
    }
    setRuleState(rule.id, "running");
    const sep      = basePath.includes("\\") ? "\\" : "/";
    const fullPath = rule.path
      ? (basePath ? `${basePath.replace(/[/\\]$/, "")}${sep}${rule.path}` : rule.path)
      : basePath;

    const opId  = crypto.randomUUID();
    onQueue({ label: rule.label, status: "running" });

    try {
      if (rule.type === "contents") {
        const res = await fmService.delete(conn, fullPath, true);
        onLog({ text: `${rule.label}: ${res.deleted} elementos eliminados en ${fullPath}`, kind: "success" });
        onOpDone(opId, { label: rule.label, status: "done", count: res.deleted });
        setRuleState(rule.id, "done");
      } else {
        // Pattern: find matching files in basePath and delete them
        const list = await fmService.list(conn, basePath || "/");
        const matches = list.entries.filter(
          (e) => !e.isDir && e.name.toLowerCase() === (rule.pattern ?? "").toLowerCase()
        );
        let deleted = 0;
        for (const entry of matches) {
          const p = basePath ? `${basePath.replace(/[/\\]$/, "")}${sep}${entry.name}` : entry.name;
          await fmService.delete(conn, p, false);
          deleted++;
        }
        onLog({ text: `${rule.label}: ${deleted} archivo(s) eliminado(s)`, kind: deleted > 0 ? "success" : "info" });
        onOpDone(opId, { label: rule.label, status: "done", count: deleted });
        setRuleState(rule.id, "done");
      }
      setTimeout(() => setRuleState(rule.id, "idle"), 3000);
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? "Error";
      onLog({ text: `Error en ${rule.label}: ${msg}`, kind: "error" });
      onOpDone(opId, { label: rule.label, status: "error", error: msg });
      setRuleState(rule.id, "error");
      setTimeout(() => setRuleState(rule.id, "idle"), 4000);
    }
  }

  function handleAdd() {
    if (!newLabel.trim()) return;
    addQuickRule({ label: newLabel.trim(), path: newPath.trim(), type: newType, pattern: newPattern.trim() || undefined });
    setNewLabel(""); setNewPath(""); setNewPattern("");
    setAdding(false);
  }

  const INPUT = "w-full h-8 bg-musgo/10 border border-musgo/25 rounded-[0.5rem] px-2.5 font-mono text-xs text-crema/70 placeholder:text-crema/20 focus:outline-none focus:border-arcilla/40 transition-colors";

  return (
    <div className="flex flex-col h-full border border-musgo/20 rounded-[1rem] overflow-hidden bg-carbon">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 bg-musgo/10 border-b border-musgo/20 shrink-0">
        <div className="flex items-center gap-2">
          <Zap size={13} className="text-arcilla/70" />
          <span className="font-mono text-[10px] text-crema/50 uppercase tracking-widest">Limpieza rápida</span>
        </div>
        <button onClick={() => setAdding((v) => !v)}
          className="w-5 h-5 flex items-center justify-center rounded text-crema/30 hover:text-crema/70 transition-colors">
          <Plus size={12} />
        </button>
      </div>

      {/* Add rule form */}
      {adding && (
        <div className="p-3 border-b border-musgo/15 space-y-2 bg-musgo/5 shrink-0">
          <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="Nombre de la regla" className={INPUT} />
          <input value={newPath}  onChange={(e) => setNewPath(e.target.value)}  placeholder="Ruta (relativa al panel)" className={INPUT} />
          <div className="grid grid-cols-2 gap-2">
            {(["contents", "pattern"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setNewType(t)}
                className={cn("h-7 rounded-[0.5rem] border font-mono text-[10px] transition-colors",
                  newType === t ? "bg-arcilla/10 border-arcilla/35 text-arcilla/80" : "bg-musgo/10 border-musgo/20 text-crema/35 hover:border-musgo/40")}>
                {t === "contents" ? "Vaciar carpeta" : "Por patrón"}
              </button>
            ))}
          </div>
          {newType === "pattern" && (
            <input value={newPattern} onChange={(e) => setNewPattern(e.target.value)} placeholder="Nombre de archivo (ej. BD_log.txt)" className={INPUT} />
          )}
          <div className="flex gap-2">
            <button onClick={() => setAdding(false)} className="flex-1 h-7 rounded-[0.5rem] border border-musgo/25 font-mono text-[10px] text-crema/35 hover:text-crema/60 transition-colors">
              Cancelar
            </button>
            <button onClick={handleAdd} disabled={!newLabel.trim()}
              className="flex-1 h-7 rounded-[0.5rem] bg-arcilla/10 border border-arcilla/30 font-mono text-[10px] text-arcilla/80 hover:bg-arcilla/15 disabled:opacity-30 transition-colors">
              Guardar
            </button>
          </div>
        </div>
      )}

      {/* Rules list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {!conn && (
          <p className="font-mono text-[10px] text-crema/20 text-center py-4">
            Conecta un servidor para ejecutar reglas
          </p>
        )}
        {quickRules.map((rule) => {
          const state = states[rule.id] ?? "idle";
          return (
            <div key={rule.id}
              className={cn(
                "group flex items-center gap-2 rounded-[0.625rem] border px-3 py-2.5 transition-colors",
                state === "done"    ? "border-green-700/30 bg-green-900/10" :
                state === "error"   ? "border-red-700/30 bg-red-900/10" :
                state === "running" ? "border-arcilla/30 bg-arcilla/5" :
                "border-musgo/20 bg-musgo/5 hover:border-musgo/35"
              )}>
              {/* Icon */}
              <div className="shrink-0">
                {state === "running" && <Loader2 size={12} className="text-arcilla/70 animate-spin" />}
                {state === "done"    && <CheckCircle2 size={12} className="text-green-400" />}
                {state === "error"   && <AlertCircle size={12} className="text-red-400" />}
                {state === "idle"    && <Zap size={12} className="text-arcilla/40" />}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="font-mono text-[10px] text-crema/70 truncate">{rule.label}</p>
                <p className="font-mono text-[9px] text-crema/25 truncate">
                  {rule.type === "contents" ? `Vaciar: ${rule.path || "(ruta actual)"}` : `Eliminar: ${rule.pattern}`}
                </p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => runRule(rule)}
                  disabled={!conn || state === "running"}
                  className="h-6 px-2 rounded-[0.375rem] bg-arcilla/10 border border-arcilla/25 font-mono text-[9px] text-arcilla/70 hover:bg-arcilla/20 disabled:opacity-30 transition-colors"
                >
                  Ejecutar
                </button>
                <button
                  onClick={() => removeQuickRule(rule.id)}
                  className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded text-crema/20 hover:text-red-400 transition-all"
                >
                  <X size={10} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
