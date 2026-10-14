"use client";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
interface ChartDay {
  date:      string;
  completed: number;
  failed:    number;
  running:   number;
}

function shortDate(iso: string) {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("es", { month: "short", day: "numeric" });
}

type HeatmapRange = 7 | 30 | 84;

function dayTotal(day: ChartDay) {
  return day.completed + day.failed + day.running;
}

function heatColor(day: ChartDay, maxTotal: number) {
  const total = dayTotal(day);
  if (total === 0) return "rgb(var(--color-musgo) / 0.12)";
  const intensity = 0.28 + (total / Math.max(maxTotal, 1)) * 0.62;
  if (day.failed > 0) return `rgb(var(--color-danger) / ${intensity})`;
  if (day.running > 0) return `rgb(var(--color-warning) / ${intensity})`;
  return `rgb(var(--color-success) / ${intensity})`;
}

export function BackupHeatmap({ days }: { days: ChartDay[] }) {
  const [range, setRange] = useState<HeatmapRange>(30);
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
          <p className="font-sans text-sm font-medium text-crema">Actividad de backups</p>
          <p className="mt-1 font-sans text-xs text-subtle">Cada cuadro representa un día · {successRate}% de éxito</p>
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
                "rounded-[0.4rem] px-3 py-1.5 font-sans text-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-arcilla/70",
                range === value
                  ? "bg-crema/10 text-crema"
                  : "text-subtle hover:text-muted",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-[0.55rem] border border-musgo/15 bg-crema/[0.035] px-3 py-2.5">
            <p className="font-sans text-xs text-subtle">{stat.label}</p>
            <p className="mt-0.5 font-sans text-lg font-semibold tabular-nums text-crema">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto pb-2">
        <div className="flex min-w-max items-start gap-2">
          <div className="grid grid-rows-7 gap-1 pt-px" aria-hidden="true">
            {["L", "M", "M", "J", "V", "S", "D"].map((label, index) => (
              <span key={`${label}-${index}`} className="flex h-4 w-3 items-center justify-center font-sans text-xs text-subtle">
                {label}
              </span>
            ))}
          </div>
          <div className="grid grid-flow-col grid-rows-7 gap-1">
            {Array.from({ length: leadingEmpty }).map((_, index) => (
              <span key={`empty-${index}`} className="h-4 w-4" aria-hidden="true" />
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
                    "h-4 w-4 rounded-[0.24rem] border border-crema/[0.035] transition duration-150 hover:scale-110 hover:border-crema/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-arcilla",
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
          <p className="font-sans text-xs text-muted" role="status">
            <span className="text-crema">{shortDate(selected.date)}</span>
            {` · ${selected.completed} completados · ${selected.failed} fallidos · ${selected.running} en ejecución`}
          </p>
        ) : (
          <p className="font-sans text-xs text-subtle">Selecciona un día para ver el detalle</p>
        )}
        <div className="flex items-center gap-3 font-sans text-xs text-subtle" aria-label="Leyenda de estados">
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-[0.15rem] bg-green-400/70" />Correcto</span>
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-[0.15rem] bg-red-400/70" />Con fallos</span>
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-[0.15rem] bg-amber-400/70" />En curso</span>
        </div>
      </div>
    </div>
  );
}

