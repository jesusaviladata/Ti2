"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import {
  Monitor, CheckCircle2, XCircle, Clock, Wifi, RefreshCw, ShieldAlert, ArrowUpRight,
} from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader, SURFACE } from "@/components/ui/page-header";

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

const SEGMENTS = [
  { key: "completed", label: "completados", color: "bg-green-400/85" },
  { key: "failed",    label: "fallidos",    color: "bg-red-400/90" },
  { key: "running",   label: "en ejecución", color: "bg-amber-400/90" },
] as const;

// ── Barras diarias apiladas ──────────────────────────────────────────────────
function BackupActivityChart({ days }: { days: ChartDay[] }) {
  const [range, setRange] = useState<HeatmapRange>(30);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const visibleDays = useMemo(() => days.slice(-range), [days, range]);
  const selected = visibleDays.find((day) => day.date === selectedDate) ?? null;

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
  const successRate = finishedTotal > 0 ? Math.round((totals.completed / finishedTotal) * 100) : null;
  const maxTotal = visibleDays.reduce((max, day) => Math.max(max, dayTotal(day)), 0);

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-[15px] font-semibold text-crema">Actividad de backups</h2>
          <p className="mt-1 text-sm text-crema/60">
            <span className="tabular-nums text-crema/85">{backupTotal}</span> backups
            {" · "}
            <span className="tabular-nums text-crema/85">{totals.failed}</span> con fallos
            {" · "}
            <span className="tabular-nums text-crema/85">{totals.activeDays}</span> días activos
            {successRate !== null ? (
              <>
                {" · "}
                <span className="tabular-nums text-crema/85">{successRate}%</span> de éxito
              </>
            ) : null}
          </p>
        </div>
        <div className="flex w-fit rounded-[0.6rem] border border-crema/[0.08] p-0.5" role="group" aria-label="Periodo del calendario">
          {([
            [84, "12 semanas"],
            [30, "30 días"],
            [7, "7 días"],
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
                "rounded-[0.45rem] px-2.5 py-1 text-xs transition-colors duration-150",
                range === value
                  ? "bg-crema/[0.09] font-medium text-crema"
                  : "text-crema/55 hover:text-crema",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        {/* Escala: máximo y cero */}
        <div className="flex h-36 w-6 shrink-0 flex-col justify-between text-right text-[11px] tabular-nums text-crema/45" aria-hidden="true">
          <span className="-mt-1.5">{maxTotal > 0 ? maxTotal : ""}</span>
          <span className="-mb-1.5">0</span>
        </div>
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              "relative flex h-36 items-end border-b border-crema/15",
              range === 84 ? "gap-px sm:gap-[2px]" : range === 30 ? "gap-[2px] sm:gap-1" : "justify-around gap-2 sm:gap-3",
            )}
          >
            <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 border-t border-dashed border-crema/[0.08]" />
            <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed border-crema/[0.08]" />
            {visibleDays.map((day) => {
              const total = dayTotal(day);
              const isSelected = selected?.date === day.date;
              const dimmed = selected !== null && !isSelected;
              const description = `${shortDate(day.date)}: ${total} backups; ${day.completed} completados, ${day.failed} fallidos y ${day.running} en ejecución`;
              return (
                <button
                  key={day.date}
                  type="button"
                  title={description}
                  aria-label={description}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedDate(isSelected ? null : day.date)}
                  className={cn("group relative flex h-full min-w-0 flex-1 flex-col-reverse rounded-t-[3px] outline-offset-2", range === 7 && "max-w-14")}
                >
                  {/* zona de clic completa; el fondo marca el día al pasar o seleccionar */}
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute inset-0 rounded-t-[3px] transition-colors duration-150",
                      isSelected ? "bg-arcilla/[0.12]" : "group-hover:bg-crema/[0.05]",
                    )}
                  />
                  {total === 0 ? (
                    <span aria-hidden="true" className="relative h-[3px] w-full rounded-[2px] bg-crema/[0.12]" />
                  ) : (
                    <span
                      aria-hidden="true"
                      className={cn(
                        "relative flex w-full flex-col-reverse gap-px overflow-hidden rounded-t-[3px] transition-opacity duration-150",
                        dimmed && "opacity-40",
                      )}
                      style={{ height: `${(total / Math.max(maxTotal, 1)) * 100}%` }}
                    >
                      {SEGMENTS.map(({ key, color }) =>
                        day[key] > 0 ? (
                          <span key={key} className={cn("w-full min-h-[2px]", color)} style={{ flexGrow: day[key] }} />
                        ) : null,
                      )}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-crema/50" aria-hidden="true">
            <span>{visibleDays[0] ? shortDate(visibleDays[0].date) : ""}</span>
            {visibleDays.length > 2 ? <span>{shortDate(visibleDays[Math.floor(visibleDays.length / 2)].date)}</span> : null}
            <span>Hoy</span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-crema/[0.06] pt-3">
        <p className="text-sm text-crema/60" role="status">
          {selected ? (
            <>
              <span className="font-medium text-crema">{shortDate(selected.date)}</span>
              {` · ${selected.completed} completados · ${selected.failed} fallidos · ${selected.running} en ejecución`}
            </>
          ) : (
            "Selecciona un día para ver el detalle"
          )}
        </p>
        <div className="flex items-center gap-3 text-xs text-crema/55" aria-label="Leyenda de estados">
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-[0.2rem] bg-green-400/85" />Correctos</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-[0.2rem] bg-red-400/90" />Con fallos</span>
          <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-[0.2rem] bg-amber-400/90" />En curso</span>
        </div>
      </div>
    </div>
  );
}

// ── Franja de métricas ───────────────────────────────────────────────────────
type Tone = "neutral" | "danger" | "warning";

function Metric({ label, value, context, href, tone }: {
  label: string; value: number; context: string; href: string; tone: Tone;
}) {
  const alert = value > 0 && tone !== "neutral";
  return (
    <Link
      href={href}
      aria-label={`${label}: ${value}. ${context}. Ver detalle`}
      className="group relative flex flex-col gap-1 bg-carbon px-4 py-4 transition-colors duration-150 hover:bg-musgo/25 sm:px-5"
    >
      <span className="flex items-center justify-between gap-2 text-sm text-crema/65">
        {label}
        <ArrowUpRight
          size={14}
          aria-hidden="true"
          className="text-crema/0 transition-colors duration-150 group-hover:text-crema/50"
        />
      </span>
      <span
        className={cn(
          "text-[1.75rem] font-semibold leading-none tracking-[-0.02em] tabular-nums",
          alert ? (tone === "danger" ? "text-red-300" : "text-amber-300") : "text-crema",
        )}
      >
        {value}
      </span>
      <span className="text-xs text-crema/50">{context}</span>
    </Link>
  );
}

// ── Actividad reciente ───────────────────────────────────────────────────────
function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  function icon(ev: ActivityEvent) {
    if (ev.kind === "backup") {
      if (ev.status === "completed") return <CheckCircle2 size={15} className="text-green-400/80" />;
      if (ev.status === "failed")    return <XCircle      size={15} className="text-red-400/80"   />;
      return <Clock size={15} className="text-arcilla/80" />;
    }
    if (ev.status === "alert") return <ShieldAlert size={15} className="text-amber-400/80" />;
    if (ev.status === "active") return <Wifi size={15} className="text-green-400/80" />;
    return <Monitor size={15} className="text-crema/45" />;
  }

  if (!events.length) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-crema/65">Sin actividad reciente</p>
        <p className="mt-1 text-xs text-crema/45">Aquí aparecerán los backups y los accesos remotos.</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-crema/[0.05]">
      {events.map((ev) => (
        <li key={ev.id} className="flex items-center gap-3 py-2.5">
          <span className="shrink-0">{icon(ev)}</span>
          <span className="min-w-0 flex-1 truncate text-sm text-crema/80">{ev.label}</span>
          <time dateTime={ev.ts} className="shrink-0 text-xs tabular-nums text-crema/50">{shortTime(ev.ts)}</time>
        </li>
      ))}
    </ul>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [summary,  setSummary]  = useState<Summary | null>(null);
  const [chart,    setChart]    = useState<ChartDay[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [failed,   setFailed]   = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
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
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const metrics = summary ? [
    { label: "Backups hoy",      value: summary.backups_today,   context: "Completados hoy",                href: "/dashboard/backups", tone: "neutral" as const },
    { label: "Backups fallidos", value: summary.failed_backups,  context: "Histórico total",                href: "/dashboard/backups", tone: "danger"  as const },
    { label: "Alertas críticas", value: summary.critical_alerts, context: "Fallos y accesos sospechosos",   href: "/dashboard/alerts",  tone: "warning" as const },
    { label: "Sesiones activas", value: summary.active_sessions, context: "Accesos remotos abiertos ahora", href: "/dashboard/access",  tone: "neutral" as const },
  ] : [];

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader
        title="Resumen general"
        description={
          failed
            ? "No se pudo actualizar el resumen. Se reintentará en 30 segundos."
            : lastSync
              ? `Actualizado a las ${lastSync.toLocaleTimeString("es", { timeStyle: "short" })} · se refresca cada 30 segundos`
              : "Cargando el estado de la plataforma…"
        }
        actions={
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex h-9 items-center gap-2 rounded-[0.6rem] border border-crema/10 px-3 text-sm text-crema/75 transition-colors duration-150 hover:border-crema/20 hover:text-crema disabled:opacity-60"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Actualizar
          </button>
        }
      />

      {/* Métricas: una franja, no cuatro tarjetas */}
      <section aria-label="Indicadores principales" className="overflow-hidden rounded-[0.9rem] border border-crema/[0.07]">
        <div className="grid grid-cols-2 gap-px bg-crema/[0.07] lg:grid-cols-4">
          {summary
            ? metrics.map((m) => <Metric key={m.label} {...m} />)
            : Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="space-y-2 bg-carbon px-5 py-4" aria-hidden="true">
                  <div className="h-4 w-24 animate-pulse rounded bg-crema/[0.06]" />
                  <div className="h-7 w-10 animate-pulse rounded bg-crema/[0.08]" />
                  <div className="h-3 w-32 animate-pulse rounded bg-crema/[0.05]" />
                </div>
              ))}
        </div>
      </section>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className={cn(SURFACE, "p-5")}>
          {chart.length === 0 ? (
            <div className="py-12 text-center">
              <h2 className="text-[15px] font-semibold text-crema">Actividad de backups</h2>
              <p className="mt-1 text-sm text-crema/60">
                {loading ? "Cargando actividad…" : "Todavía no hay backups registrados."}
              </p>
            </div>
          ) : (
            <BackupActivityChart days={chart} />
          )}
        </section>

        <section className={cn(SURFACE, "flex max-h-[460px] flex-col p-5")}>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-crema">Actividad reciente</h2>
            <Link href="/dashboard/alerts" className="text-xs text-arcilla hover:underline hover:underline-offset-4">
              Ver todo
            </Link>
          </div>
          <div className="-mr-2 overflow-y-auto pr-2">
            <ActivityFeed events={activity} />
          </div>
        </section>
      </div>
    </div>
  );
}
