"use client";

import { useEffect, useState, useCallback } from "react";
import { Bell, AlertTriangle, ShieldAlert, CheckCircle2, RefreshCw } from "lucide-react";
import api from "@/lib/api";

interface Notification {
  id:    string;
  kind:  "backup_fail" | "suspicious";
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

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api/v1/notifications");
      setItems(data.notifications ?? []);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Centro de alertas</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Notificaciones<span className="text-arcilla">.</span>
          </h1>
        </div>
        <button
          onClick={load}
          className="w-7 h-7 flex items-center justify-center rounded-[0.5rem] border border-musgo/25 text-crema/30 hover:text-crema/70 transition-colors"
          aria-label="Actualizar"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* List */}
      <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 overflow-hidden">
        {loading ? (
          <div className="p-10 text-center">
            <p className="font-mono text-xs text-crema/25">Cargando…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center text-center gap-3">
            <div className="w-12 h-12 rounded-[0.75rem] bg-musgo/20 flex items-center justify-center">
              <CheckCircle2 size={20} className="text-crema/25" />
            </div>
            <p className="font-sans text-sm text-crema/50">Sin notificaciones</p>
            <p className="font-mono text-xs text-crema/25">
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
                  {n.kind === "backup_fail"
                    ? <AlertTriangle size={15} className="text-red-400/80" />
                    : <ShieldAlert   size={15} className="text-orange-400/80" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-sans text-sm font-medium text-crema/85">{n.title}</p>
                  <p className="font-mono text-[11px] text-crema/40 mt-0.5 break-words">{n.body}</p>
                </div>
                <span className="font-mono text-[10px] text-crema/25 shrink-0 mt-0.5">{timeAgo(n.ts)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {items.length > 0 && (
        <p className="font-mono text-[10px] text-crema/25 flex items-center gap-1.5">
          <Bell size={10} /> {items.length} notificación{items.length !== 1 ? "es" : ""} · se actualiza cada 30&nbsp;s
        </p>
      )}
    </div>
  );
}
