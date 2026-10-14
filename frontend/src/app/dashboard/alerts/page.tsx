"use client";

import { useEffect, useState, useCallback } from "react";
import { Bell, AlertTriangle, ShieldAlert, CheckCircle2, RefreshCw, Trash2 } from "lucide-react";
import api from "@/lib/api";

interface Notification {
  id:    string;
  kind:  "backup_fail" | "backup_success" | "suspicious" | "test";
  title: string;
  body:  string;
  ts:    string;
}

function timeAgo(iso: string) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  return `hace ${Math.floor(hrs / 24)}d`;
}

export default function AlertsPage() {
  const [items,   setItems]   = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api/v1/notifications");
      setItems(data.notifications ?? []);
    } catch {}
    finally { setLoading(false); }
  }, []);

  const clear = useCallback(async () => {
    setClearing(true);
    try {
      await api.delete("/api/v1/notifications");
      setItems([]);
      window.dispatchEvent(new Event("data-express:notifications-cleared"));
    } finally {
      setClearing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const cleared = () => setItems([]);
    window.addEventListener("data-express:notifications-cleared", cleared);
    return () => window.removeEventListener("data-express:notifications-cleared", cleared);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="font-sans text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Centro de alertas</p>
          <h1 className="font-title text-[28px] font-semibold text-crema">
            Notificaciones
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {items.length > 0 && (
            <button
              type="button"
              onClick={clear}
              disabled={clearing}
              className="flex h-8 items-center gap-1.5 rounded-[0.5rem] border border-musgo/25 px-3 font-sans text-xs text-subtle transition-colors hover:border-red-400/30 hover:text-danger disabled:opacity-40"
            >
              <Trash2 size={12} /> {clearing ? "Limpiando…" : "Limpiar"}
            </button>
          )}
          <button
            onClick={load}
            className="w-7 h-7 flex items-center justify-center rounded-[0.5rem] border border-musgo/25 text-subtle hover:text-crema transition-colors"
            aria-label="Actualizar"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="rounded-xl bg-surface border border-musgo/20 overflow-hidden">
        {loading ? (
          <div className="p-10 text-center">
            <p className="font-sans text-xs text-subtle">Cargando…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center text-center gap-3">
            <div className="w-12 h-12 rounded-[0.75rem] bg-surface flex items-center justify-center">
              <CheckCircle2 size={20} className="text-subtle" />
            </div>
            <p className="font-sans text-sm text-muted">Sin notificaciones</p>
            <p className="font-sans text-xs text-subtle">
              Aquí aparecerán backups fallidos y accesos sospechosos.
            </p>
          </div>
        ) : (
          <div>
            {items.map((n) => (
              <div
                key={n.id}
                className="flex items-start gap-3 px-5 py-4 border-b border-musgo/10 last:border-0 hover:bg-musgo/10 transition-colors"
              >
                <div className="mt-0.5 shrink-0">
                  {n.kind === "backup_fail" && <AlertTriangle size={15} className="text-danger" />}
                  {n.kind === "backup_success" && <CheckCircle2 size={15} className="text-success" />}
                  {n.kind !== "backup_fail" && n.kind !== "backup_success" && <ShieldAlert size={15} className="text-warning" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-sans text-sm font-medium text-crema">{n.title}</p>
                  <p className="font-sans text-xs text-muted mt-0.5 break-words">{n.body}</p>
                </div>
                <span className="font-sans text-xs text-subtle shrink-0 mt-0.5">{timeAgo(n.ts)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {items.length > 0 && (
        <p className="font-sans text-xs text-subtle flex items-center gap-1.5">
          <Bell size={10} /> {items.length} notificación{items.length !== 1 ? "es" : ""} · se actualiza cada 30&nbsp;s
        </p>
      )}
    </div>
  );
}
