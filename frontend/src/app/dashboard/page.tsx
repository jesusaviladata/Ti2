"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  Database, Monitor, AlertTriangle, CheckCircle2,
  XCircle, Clock, Wifi, RefreshCw, ShieldAlert,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Summary {
  backups_today:   number;
  failed_backups:  number;
  active_sessions: number;
  critical_alerts: number;
}

interface ChartDay {
  date:      string;
  completed: number;
  failed:    number;
  running:   number;
}

interface ActivityEvent {
  id:     string;
  kind:   "backup" | "access";
  label:  string;
  status: string;
  ts:     string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function shortDate(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es", { month: "short", day: "numeric" });
}

function shortTime(iso: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("es", { timeStyle: "short" });
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[0.75rem] border border-musgo/30 bg-carbon px-3 py-2 shadow-xl">
      <p className="font-mono text-[10px] text-crema/40 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} className="font-mono text-xs" style={{ color: p.fill }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricCard({ label, value, sub, icon: Icon, color, bg, href }: {
  label: string; value: number | string; sub: string;
  icon: React.ElementType; color: string; bg: string; href: string;
}) {
  return (
    <Link
      href={href}
      aria-label={`${label}: ${value}. Ver detalle`}
      className="group block rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5 hover:border-arcilla/40 focus-visible:border-arcilla/50 focus-visible:outline-none transition-colors"
    >
      <div className={cn("w-9 h-9 rounded-[0.75rem] flex items-center justify-center mb-4", bg)}>
        <Icon size={17} className={color} />
      </div>
      <p className="font-display text-4xl italic font-light text-crema/90 mb-0.5">{value}</p>
      <p className="font-sans text-sm text-crema/60 group-hover:text-crema/80 transition-colors">{label}</p>
      <p className="font-mono text-[10px] text-crema/25 mt-2">{sub}</p>
    </Link>
  );
}

// ── Activity feed ─────────────────────────────────────────────────────────────
function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  function icon(ev: ActivityEvent) {
    if (ev.kind === "backup") {
      if (ev.status === "completed") return <CheckCircle2 size={12} className="text-green-400/70" />;
      if (ev.status === "failed")    return <XCircle      size={12} className="text-red-400/70"   />;
      return <Clock size={12} className="text-arcilla/60" />;
    }
    if (ev.status === "alert") return <ShieldAlert size={12} className="text-orange-400/70" />;
    if (ev.status === "active") return <Wifi size={12} className="text-green-400/70" />;
    return <Monitor size={12} className="text-crema/30" />;
  }

  if (!events.length) {
    return <p className="font-mono text-xs text-crema/20 py-4 text-center">Sin actividad reciente</p>;
  }

  return (
    <div className="space-y-1">
      {events.map((ev) => (
        <div key={ev.id} className="flex items-center gap-3 px-1 py-2 rounded-[0.5rem] hover:bg-musgo/10 transition-colors">
          <div className="shrink-0">{icon(ev)}</div>
          <span className="flex-1 font-mono text-xs text-crema/60 truncate">{ev.label}</span>
          <span className="font-mono text-[10px] text-crema/25 shrink-0">{shortTime(ev.ts)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [summary,  setSummary]  = useState<Summary | null>(null);
  const [chart,    setChart]    = useState<ChartDay[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, c, a] = await Promise.all([
        api.get("/api/v1/dashboard/summary").then((r) => r.data),
        api.get("/api/v1/dashboard/backup-chart").then((r) => r.data),
        api.get("/api/v1/dashboard/activity").then((r) => r.data),
      ]);
      setSummary(s);
      setChart(c.chart);
      setActivity(a.activity);
      setLastSync(new Date());
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const cards = summary ? [
    {
      label: "Backups hoy",
      value: summary.backups_today,
      sub:   "completados hoy",
      icon:  Database,
      color: "text-green-400",
      bg:    "bg-green-900/20",
      href:  "/dashboard/backups",
    },
    {
      label: "Sesiones activas",
      value: summary.active_sessions,
      sub:   "accesos abiertos ahora",
      icon:  Monitor,
      color: "text-blue-400",
      bg:    "bg-blue-900/20",
      href:  "/dashboard/access",
    },
    {
      label: "Backups fallidos",
      value: summary.failed_backups,
      sub:   "en total",
      icon:  XCircle,
      color: "text-red-400",
      bg:    "bg-red-900/20",
      href:  "/dashboard/backups",
    },
    {
      label: "Alertas críticas",
      value: summary.critical_alerts,
      sub:   "fallos + accesos sospechosos",
      icon:  AlertTriangle,
      color: "text-orange-400",
      bg:    "bg-orange-900/20",
      href:  "/dashboard/alerts",
    },
  ] : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Panel principal</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Resumen general<span className="text-arcilla">.</span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {lastSync && (
            <span className="font-mono text-[10px] text-crema/25">
              Actualizado {lastSync.toLocaleTimeString("es", { timeStyle: "short" })}
            </span>
          )}
          <button onClick={load}
            className="w-7 h-7 flex items-center justify-center rounded-[0.5rem] border border-musgo/25 text-crema/30 hover:text-crema/70 transition-colors">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-36 rounded-[1.25rem] bg-musgo/10 border border-musgo/15 animate-pulse" />
            ))
          : cards.map((c) => <MetricCard key={c.label} {...c} />)
        }
      </div>

      {/* Chart + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* Backup chart */}
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          <p className="font-sans text-sm font-medium text-crema/70 mb-5">Backups — últimos 14 días</p>
          {chart.length === 0 ? (
            <div className="h-48 flex items-center justify-center">
              <p className="font-mono text-xs text-crema/20">Sin datos de backups aún</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chart} barGap={2} barCategoryGap="30%">
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDate}
                  tick={{ fontFamily: "var(--font-mono)", fontSize: 9, fill: "rgba(242,240,233,0.25)" }}
                  axisLine={false} tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontFamily: "var(--font-mono)", fontSize: 9, fill: "rgba(242,240,233,0.20)" }}
                  axisLine={false} tickLine={false} width={20}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(46,64,54,0.3)" }} />
                <Bar dataKey="completed" name="Completados" fill="#4ade80" radius={[3,3,0,0]} opacity={0.7} />
                <Bar dataKey="failed"    name="Fallidos"    fill="#f87171" radius={[3,3,0,0]} opacity={0.7} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Activity feed */}
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          <p className="font-sans text-sm font-medium text-crema/70 mb-4">Actividad reciente</p>
          <ActivityFeed events={activity} />
        </div>
      </div>
    </div>
  );
}
