"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  Database, Monitor, AlertTriangle, CheckCircle2,
  XCircle, Clock, Wifi, RefreshCw, ShieldAlert,
} from "lucide-react";
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
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("es", { month: "short", day: "numeric" });
}

function shortTime(iso: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("es", { timeStyle: "short" });
}

type HeatmapRange = 7 | 30 | 84;

function dayTotal(day: ChartDay) {
  return day.completed + day.failed + day.running;
}

function heatColor(day: ChartDay, maxTotal: number) {
  const total = dayTotal(day);
  if (total === 0) return "rgba(242, 240, 233, 0.07)";
  const intensity = 0.28 + (total / Math.max(maxTotal, 1)) * 0.62;
  if (day.failed > 0) return `rgba(248, 113, 113, ${intensity})`;
  if (day.running > 0) return `rgba(251, 191, 36, ${intensity})`;
  return `rgba(74, 222, 128, ${intensity})`;
}

function BackupHeatmap({ days }: { days: ChartDay[] }) {
  const [range, setRange] = useState<HeatmapRange>(84);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const visibleDays = useMemo(() => days.slice(-range), [days, range]);
  const selected = visibleDays.find((day) => day.date === selectedDate) ?? null;
  const leadingEmpty = visibleDays.length
    ? (new Date(`${visibleDays[0].date}T00:00:00`).getDay() + 6) % 7
    : 0;

  const totals = useMemo(() => visibleDays.reduce(
    (acc, day) => {
      acc.completed += day.completed;
      acc.failed += day.failed;
      acc.running += day.running;
      if (dayTotal(day) > 0) acc.activeDays += 1;
      return acc;
    },
    { completed: 0, failed: 0, running: 0, activeDays: 0 },
  ), [visibleDays]);
  const backupTotal = totals.completed + totals.failed + totals.running;
  const finishedTotal = totals.completed + totals.failed;
  const successRate = finishedTotal > 0 ? Math.round((totals.completed / finishedTotal) * 100) : 0;
  const maxTotal = visibleDays.reduce((max, day) => Math.max(max, dayTotal(day)), 0);

  const stats = [
    { label: "Backups", value: backupTotal },
    { label: "Completados", value: totals.completed },
    { label: "Con fallos", value: totals.failed },
    { label: "Días activos", value: totals.activeDays },
  ];

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-sans text-sm font-medium text-crema/75">Actividad de backups</p>
          <p className="mt-1 font-mono text-[10px] text-crema/30">Cada cuadro representa un día · {successRate}% de éxito</p>
        </div>
        <div className="flex w-fit rounded-[0.55rem] border border-musgo/25 bg-carbon/40 p-1" aria-label="Periodo del calendario">
          {([
            [84, "Todo"],
            [30, "30 d"],
            [7, "7 d"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setRange(value);
                setSelectedDate(null);
              }}
              aria-pressed={range === value}
              className={cn(
                "rounded-[0.4rem] px-3 py-1.5 font-mono text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-arcilla/70",
                range === value
                  ? "bg-crema/10 text-crema/90"
                  : "text-crema/35 hover:text-crema/65",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-[0.55rem] border border-musgo/15 bg-crema/[0.035] px-3 py-2.5">
            <p className="font-sans text-[11px] text-crema/35">{stat.label}</p>
            <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-crema/85">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto pb-2">
        <div className="flex min-w-max items-start gap-2">
          <div className="grid grid-rows-7 gap-1.5 pt-px" aria-hidden="true">
            {["L", "M", "M", "J", "V", "S", "D"].map((label, index) => (
              <span key={`${label}-${index}`} className="flex h-6 w-3 items-center justify-center font-mono text-[8px] text-crema/20 xl:h-7">
                {label}
              </span>
            ))}
          </div>
          <div className="grid grid-flow-col grid-rows-7 gap-1.5">
            {Array.from({ length: leadingEmpty }).map((_, index) => (
              <span key={`empty-${index}`} className="h-6 w-6 xl:h-7 xl:w-7" aria-hidden="true" />
            ))}
            {visibleDays.map((day) => {
              const total = dayTotal(day);
              const isSelected = selected?.date === day.date;
              const description = `${shortDate(day.date)}: ${total} backups; ${day.completed} completados, ${day.failed} fallidos y ${day.running} en ejecución`;
              return (
                <button
                  key={day.date}
                  type="button"
                  title={description}
                  aria-label={description}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedDate(isSelected ? null : day.date)}
                  className={cn(
                    "h-6 w-6 rounded-[0.24rem] border border-crema/[0.035] transition duration-150 hover:scale-110 hover:border-crema/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-arcilla xl:h-7 xl:w-7",
                    isSelected && "scale-110 border-arcilla/80 ring-1 ring-arcilla/70",
                  )}
                  style={{ backgroundColor: heatColor(day, maxTotal) }}
                />
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-musgo/15 pt-3">
        {selected ? (
          <p className="font-mono text-[10px] text-crema/55" role="status">
            <span className="text-crema/80">{shortDate(selected.date)}</span>
            {` · ${selected.completed} completados · ${selected.failed} fallidos · ${selected.running} en ejecución`}
          </p>
        ) : (
          <p className="font-mono text-[10px] text-crema/25">Selecciona un día para ver el detalle</p>
        )}
        <div className="flex items-center gap-3 font-mono text-[9px] text-crema/30" aria-label="Leyenda de estados">
          <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-[0.15rem] bg-green-400/70" />Correcto</span>
          <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-[0.15rem] bg-red-400/70" />Con fallos</span>
          <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-[0.15rem] bg-amber-400/70" />En curso</span>
        </div>
      </div>
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
      <p className="mb-0.5 text-4xl font-semibold tabular-nums text-crema/90">{value}</p>
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
        api.get("/api/v1/dashboard/backup-chart", { params: { days: 84 } }).then((r) => r.data),
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
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* Backup activity calendar */}
        <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          {chart.length === 0 ? (
            <div className="h-48 flex items-center justify-center">
              <p className="font-mono text-xs text-crema/20">Sin datos de backups aún</p>
            </div>
          ) : (
            <BackupHeatmap days={chart} />
          )}
        </div>

        {/* Activity feed */}
        <div className="max-h-[420px] overflow-hidden rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
          <p className="font-sans text-sm font-medium text-crema/70 mb-4">Actividad reciente</p>
          <div className="max-h-[350px] overflow-y-auto pr-1">
            <ActivityFeed events={activity} />
          </div>
        </div>
      </div>
    </div>
  );
}
