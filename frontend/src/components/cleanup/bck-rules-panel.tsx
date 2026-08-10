"use client";

import { useState } from "react";
import { Plus, Trash2, Edit2, ShieldCheck, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCleanupRules, useDeleteRule } from "@/hooks/useCleanup";
import { cn } from "@/lib/utils";
import type { CleanupRule, KeepPolicy } from "@/types/cleanup";

const KEEP_LABELS: Record<KeepPolicy, string> = {
  latest:   "Solo el más reciente",
  latest_n: "Últimos N",
  none:     "Eliminar todos",
  all:      "No eliminar (solo auditar)",
};

const KEEP_COLOR: Record<KeepPolicy, string> = {
  latest:   "text-arcilla/80 bg-arcilla/10 border-arcilla/25",
  latest_n: "text-yellow-400/80 bg-yellow-900/10 border-yellow-800/25",
  none:     "text-red-400/80 bg-red-900/10 border-red-800/25",
  all:      "text-green-400/80 bg-green-900/10 border-green-800/25",
};

export function BckRulesPanel({ onNewRule }: { onNewRule: () => void }) {
  const { data } = useCleanupRules();
  const deleteRule = useDeleteRule();
  const rules = data?.items ?? [];

  if (!rules.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-[0.75rem] bg-musgo/20 flex items-center justify-center mb-3">
          <ShieldCheck size={20} className="text-crema/20" />
        </div>
        <p className="font-sans text-sm text-crema/40">Sin reglas configuradas</p>
        <p className="font-mono text-xs text-crema/20 mt-1 mb-4">
          Crea reglas para definir qué archivos limpiar automáticamente
        </p>
        <Button variant="outline" onClick={onNewRule} className="text-xs gap-2">
          <Plus size={13} /> Nueva regla BCK
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={onNewRule} className="gap-2 text-xs h-9">
          <Plus size={13} /> Nueva regla
        </Button>
      </div>

      <div className="grid gap-3">
        {rules.map((rule) => (
          <RuleCard key={rule.id} rule={rule} onDelete={() => deleteRule.mutate(rule.id)} />
        ))}
      </div>
    </div>
  );
}

function RuleCard({ rule, onDelete }: { rule: CleanupRule; onDelete: () => void }) {
  return (
    <div className="rounded-[1rem] bg-musgo/10 border border-musgo/20 hover:border-musgo/30 transition-colors p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-[0.65rem] bg-musgo/30 flex items-center justify-center shrink-0">
            <Tag size={14} className="text-crema/50" />
          </div>
          <div className="min-w-0">
            <p className="font-sans text-sm text-crema/80 font-medium">{rule.name}</p>
            <p className="font-mono text-[10px] text-crema/30 mt-0.5">
              {rule.folderId ? "Carpeta específica" : "Todas las carpetas"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <span className={cn(
            "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono border",
            rule.enabled ? "bg-green-900/15 text-green-400/70 border-green-800/25" : "bg-musgo/20 text-crema/30 border-musgo/30"
          )}>
            <span className={cn("w-1.5 h-1.5 rounded-full mr-1.5", rule.enabled ? "bg-green-400" : "bg-crema/20")} />
            {rule.enabled ? "activa" : "inactiva"}
          </span>

          <button
            onClick={onDelete}
            className="w-7 h-7 rounded-[0.5rem] flex items-center justify-center text-crema/20 hover:bg-red-900/20 hover:text-red-400 transition-colors"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Details */}
      <div className="mt-3 pt-3 border-t border-musgo/15 flex flex-wrap gap-2">
        {rule.patterns.map((p) => (
          <span key={p} className="px-2 py-0.5 rounded-md bg-musgo/20 border border-musgo/30 font-mono text-[10px] text-crema/50">
            {p}
          </span>
        ))}
        {rule.extensions.map((e) => (
          <span key={e} className="px-2 py-0.5 rounded-md bg-arcilla/5 border border-arcilla/20 font-mono text-[10px] text-arcilla/60">
            {e}
          </span>
        ))}

        <span className={cn(
          "ml-auto px-2.5 py-0.5 rounded-full text-[10px] font-mono border",
          KEEP_COLOR[rule.keep]
        )}>
          {KEEP_LABELS[rule.keep]}
          {rule.keep === "latest_n" && ` (${rule.keepN})`}
        </span>
      </div>

      {rule.minAgeDays > 0 && (
        <p className="font-mono text-[10px] text-crema/25 mt-2">
          Mínimo {rule.minAgeDays} día{rule.minAgeDays !== 1 ? "s" : ""} de antigüedad para eliminar
        </p>
      )}
    </div>
  );
}
