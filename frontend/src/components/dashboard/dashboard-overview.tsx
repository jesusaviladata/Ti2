"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Database, Monitor, RefreshCw, Server, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import { useAgents } from "@/hooks/useAgents";
import { useBackupList } from "@/hooks/useBackups";
import { agentState } from "@/components/agents/agent-table";
import { BackupHeatmap } from "./backup-heatmap";
import type { BackupRecord } from "@/types/backup";
import { cn, formatBytes } from "@/lib/utils";

interface Summary { backups_today: number; failed_backups: number; active_sessions: number; critical_alerts: number }
interface Activity { id: string; kind: "backup" | "access"; label: string; status: string; ts: string }
interface ChartDay { date: string; completed: number; failed: number; running: number }

function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" }) : "—";
}

function backupState(backup: BackupRecord) {
  if (backup.status === "failed" || backup.deliveryStatus === "failed") return { label: backup.deliveryStatus === "failed" ? "Entrega fallida" : "Fallido", tone: "bg-danger/10 text-danger" };
  if (backup.status === "pending") return { label: "En cola", tone: "bg-warning/10 text-warning" };
  if (backup.status === "running" || ["pending", "processing"].includes(backup.deliveryStatus ?? "")) return { label: "En ejecución", tone: "bg-arcilla/10 text-arcilla" };
  return { label: "Completado", tone: "bg-success/10 text-success" };
}

function RunningBackup({ backup }: { backup: BackupRecord }) {
  const delivering = backup.status === "completed";
  const raw = delivering ? backup.deliveryProgress : backup.progressPercent;
  const known = typeof raw === "number" && Number.isFinite(raw);
  const percent = known ? Math.min(100, Math.max(0, raw)) : 0;
  return <div className="border-t border-musgo/15 px-5 py-4">
    <div className="flex items-center justify-between gap-3"><p className="truncate text-sm font-medium">{backup.databaseName}</p><span className="text-xs tabular-nums text-arcilla">{known ? `${Math.round(percent)}%` : "En curso"}</span></div>
    <p className="mt-1 truncate text-xs text-subtle">{backup.origin?.agent.hostname ?? "Servidor sin identificar"} · {delivering ? "Preparando entrega" : backup.status === "pending" ? "Esperando al agente" : "Copia SQL en curso"}</p>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-inset" role="progressbar" aria-label={`Progreso de ${backup.databaseName}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={known ? percent : undefined} aria-valuetext={!known ? "Esperando progreso del agente" : undefined}><div className={cn("h-full rounded-full bg-arcilla transition-[width]", !known && "w-1/4 motion-safe:animate-pulse")} style={known ? { width: `${percent}%` } : undefined} /></div>
  </div>;
}

export function DashboardOverview() {
  const summary = useQuery({ queryKey: ["dashboard", "summary"], queryFn: () => api.get<Summary>("/api/v1/dashboard/summary").then((r) => r.data), refetchInterval: 30_000 });
  const activity = useQuery({ queryKey: ["dashboard", "activity"], queryFn: () => api.get<{ activity: Activity[] }>("/api/v1/dashboard/activity").then((r) => r.data.activity), refetchInterval: 30_000 });
  const chart = useQuery({ queryKey: ["dashboard", "chart"], queryFn: () => api.get<{ chart: ChartDay[] }>("/api/v1/dashboard/backup-chart", { params: { days: 84 } }).then((r) => r.data.chart), refetchInterval: 60_000 });
  const agents = useAgents();
  const backups = useBackupList(0, 50);
  const servers = agents.data?.items ?? [];
  const connected = servers.filter((agent) => agent.online && !agentState(agent).incident).length;
  const incidents = servers.filter((agent) => agentState(agent).incident);
  const records = backups.data?.items ?? [];
  const running = records.filter((backup) => backup.status === "pending" || backup.status === "running" || (backup.status === "completed" && ["pending", "processing"].includes(backup.deliveryStatus ?? "")));
  const hasHistory = chart.data?.some((day) => day.completed + day.failed + day.running > 0);
  const refreshing = summary.isFetching || agents.isFetching || backups.isFetching;
  const metrics = [
    { label: "Copias completadas hoy", value: summary.isError ? "—" : summary.data?.backups_today ?? "—", detail: "Copias SQL registradas hoy", icon: Database, href: "/dashboard/backups" },
    { label: "Servidores conectados", value: agents.isError || agents.isLoading ? "—" : `${connected} / ${servers.length}`, detail: "Agentes disponibles y sin incidencias", icon: Server, href: "/dashboard/servers" },
    { label: "Alertas críticas", value: summary.isError ? "—" : summary.data?.critical_alerts ?? "—", detail: "Revisa los eventos que requieren atención", icon: AlertTriangle, href: "/dashboard/alerts" },
  ];

  function refresh() {
    void summary.refetch(); void activity.refetch(); void chart.refetch(); void agents.refetch(); void backups.refetch();
  }

  return <div className="mx-auto max-w-[1500px] space-y-6">
    <div className="de-page-heading">
      <div><p className="de-eyebrow">Panel principal / Resumen</p><h1 className="de-page-title">Resumen general</h1><p className="mt-2 text-sm text-muted">Supervisa tus servidores y el estado de tus copias.</p></div>
      <button type="button" className="de-filter flex items-center gap-2" onClick={refresh} disabled={refreshing}><RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />Actualizar</button>
    </div>

    {summary.isError ? <p role="alert" className="rounded-lg border border-danger/25 bg-danger/5 px-4 py-3 text-sm text-danger">No se pudo actualizar el resumen. Usa Actualizar para reintentarlo.</p> : null}

    <div className="grid gap-4 sm:grid-cols-3">
      {metrics.map(({ label, value, detail, icon: Icon, href }) => <Link key={label} href={href} className="de-panel p-5 transition-colors hover:border-arcilla/40">
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-medium text-muted">{label}</p><Icon size={18} className="shrink-0 text-arcilla" /></div>
        <p className="mb-2 mt-4 text-[32px] font-semibold leading-none tabular-nums">{value}</p><p className="text-xs text-subtle">{detail}</p>
      </Link>)}
    </div>

    {incidents.length ? <Link href="/dashboard/servers" className="flex items-start gap-3 rounded-lg border border-warning/25 bg-warning/5 px-4 py-3 text-warning"><AlertTriangle size={19} className="mt-0.5 shrink-0" /><div><p className="text-sm font-medium">{incidents.length} {incidents.length === 1 ? "servidor necesita" : "servidores necesitan"} atención</p><p className="mt-1 text-xs">{incidents.slice(0, 3).map((agent) => `${agent.configuration?.name ?? agent.hostname}: ${agentState(agent).label.toLowerCase()}`).join(" · ")}</p></div><ArrowRight size={16} className="ml-auto shrink-0" /></Link> : null}

    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="de-panel min-w-0 overflow-hidden" aria-label="Últimas copias SQL">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"><div><h2 className="de-section-heading">Últimas copias SQL</h2><p className="mt-1 text-xs text-subtle">Las 6 más recientes</p></div><Link href="/dashboard/backups" className="flex items-center gap-1 text-xs font-medium text-arcilla">Ver historial<ArrowRight size={14} /></Link></div>
        {backups.isLoading ? <p className="de-empty" role="status">Consultando copias…</p> : backups.isError ? <p className="de-empty text-danger" role="alert">No se pudieron consultar las copias.</p> : !records.length ? <div className="de-empty"><ShieldCheck size={25} className="text-subtle" /><p className="font-medium text-crema">Todavía no hay copias registradas</p><p>Cuando un agente ejecute la primera, aparecerá aquí.</p><Link href="/dashboard/backups" className="mt-2 font-medium text-arcilla">Ir a copias SQL →</Link></div> : <div className="overflow-x-auto"><table className="de-table"><thead><tr><th>Base de datos / servidor</th><th>Estado</th><th>Tamaño</th><th>Fecha</th></tr></thead><tbody>{records.slice(0, 6).map((backup) => { const state = backupState(backup); return <tr key={backup.id}><td><Link href="/dashboard/backups" className="font-medium hover:text-arcilla">{backup.databaseName}</Link><p className="mt-1 text-xs text-subtle">{backup.origin?.agent.hostname ?? "Origen no registrado"}</p></td><td><span className={`de-badge whitespace-nowrap ${state.tone}`}>{state.label}</span></td><td className="whitespace-nowrap text-xs tabular-nums text-muted">{backup.fileSizeBytes == null ? "—" : formatBytes(backup.fileSizeBytes)}</td><td className="whitespace-nowrap text-xs text-muted">{dateTime(backup.finishedAt ?? backup.startedAt ?? backup.createdAt)}</td></tr>; })}</tbody></table></div>}
        <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-musgo/15 px-5 py-3 text-xs text-muted"><span>Fallos registrados: <strong className="font-semibold text-crema">{summary.isError ? "—" : summary.data?.failed_backups ?? "—"}</strong></span><Link href="/dashboard/access" className="flex items-center gap-1.5 hover:text-arcilla"><Monitor size={13} />Sesiones activas: {summary.isError ? "—" : summary.data?.active_sessions ?? "—"}</Link></div>
      </section>

      <section className="de-panel overflow-hidden" aria-label="Copias SQL en ejecución"><div className="flex items-center justify-between px-5 py-4"><h2 className="de-section-heading">En ejecución</h2><span className="de-badge bg-arcilla/10 text-arcilla">{backups.isLoading || backups.isError ? "—" : running.length}</span></div>{backups.isError ? <p className="de-empty text-danger">Estado no disponible</p> : backups.isLoading ? <p className="de-empty" role="status">Consultando tareas…</p> : running.length ? <>{running.slice(0, 4).map((backup) => <RunningBackup key={backup.id} backup={backup} />)}<Link href="/dashboard/backups" className="block border-t border-musgo/15 px-5 py-3 text-xs font-medium text-arcilla">Ver tareas SQL →</Link></> : <div className="de-empty border-t border-musgo/15"><CheckCircle2 size={22} className="text-subtle" /><p>Sin copias SQL en curso</p><Link href="/dashboard/file-backups" className="text-xs text-arcilla">Consultar copias de carpetas →</Link></div>}</section>
    </div>

    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="de-panel min-w-0 overflow-hidden"><div className="flex items-center justify-between gap-3 px-5 py-4"><h2 className="de-section-heading">Estado de servidores</h2><Link href="/dashboard/servers" className="text-xs font-medium text-arcilla">Ver todos →</Link></div>{agents.isLoading ? <p className="de-empty" role="status">Consultando agentes…</p> : agents.isError ? <p className="de-empty text-danger" role="alert">No se pudo consultar el estado de los servidores.</p> : !servers.length ? <div className="de-empty border-t border-musgo/15"><Server size={24} className="text-subtle" /><p className="font-medium text-crema">Conecta tu primer servidor</p><p>Vincula el agente desde la sección Servidores.</p><Link href="/dashboard/servers" className="mt-2 text-arcilla">Administrar servidores →</Link></div> : <div className="overflow-x-auto"><table className="de-table"><thead><tr><th>Servidor</th><th>Estado</th><th>Último contacto</th></tr></thead><tbody>{[...servers].sort((a, b) => Number(agentState(b).incident) - Number(agentState(a).incident)).slice(0, 5).map((agent) => { const state = agentState(agent); return <tr key={agent.id}><td className="font-medium">{agent.configuration?.name ?? agent.hostname}</td><td><span className={`de-badge whitespace-nowrap ${state.tone}`}>{state.label}</span></td><td className="whitespace-nowrap text-xs text-muted">{dateTime(agent.lastHeartbeatAt ?? agent.lastSeenAt)}</td></tr>; })}</tbody></table></div>}</section>

      <section className="de-panel"><h2 className="de-section-heading px-5 py-4">Actividad reciente</h2>{activity.isError ? <p className="de-empty text-danger">Actividad no disponible</p> : activity.isLoading ? <p className="de-empty" role="status">Consultando eventos…</p> : !activity.data?.length ? <p className="de-empty border-t border-musgo/15">Sin actividad reciente</p> : <ul>{activity.data.slice(0, 5).map((event) => <li key={event.id} className="flex gap-3 border-t border-musgo/15 px-5 py-4"><span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", event.status === "failed" || event.status === "alert" ? "bg-danger" : event.status === "completed" ? "bg-success" : "bg-arcilla")} /><div className="min-w-0"><p className="break-words text-sm text-muted">{event.label}</p><p className="mt-1 text-xs text-subtle">{dateTime(event.ts)}</p></div></li>)}</ul>}</section>
    </div>

    {hasHistory ? <details className="de-panel p-5"><summary className="cursor-pointer text-sm font-semibold">Calendario de actividad</summary><div className="mt-5"><BackupHeatmap days={chart.data ?? []} /></div></details> : null}
    <p className="text-xs text-subtle">Resumen actualizado {summary.dataUpdatedAt ? dateTime(new Date(summary.dataUpdatedAt).toISOString()) : "—"} · Copias SQL: últimas 50 consultadas</p>
  </div>;
}
