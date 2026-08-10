"use client";

import { useState, useRef, useEffect } from "react";
import { Server, ChevronDown, Check, Trash2, Plus, Wifi, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { useConnectionsStore } from "@/store/connections.store";

interface Props {
  onNewConnection: () => void;
}

export function ConnectionDropdown({ onNewConnection }: Props) {
  const { connections, activeId, setActive, removeConnection } = useConnectionsStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const active = connections.find((c) => c.id === activeId);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-2 h-9 px-3 rounded-[0.75rem] border transition-all duration-150 text-left",
          "font-mono text-xs",
          active
            ? "bg-musgo/20 border-musgo/40 text-crema/70 hover:border-musgo/60"
            : "bg-musgo/10 border-musgo/20 text-crema/35 hover:border-musgo/40"
        )}
      >
        {active ? (
          <Wifi size={13} className="text-green-400 shrink-0" />
        ) : (
          <WifiOff size={13} className="text-crema/25 shrink-0" />
        )}
        <span className="max-w-[160px] truncate">
          {active ? active.label : "Sin conexión"}
        </span>
        <ChevronDown
          size={12}
          className={cn("text-crema/30 transition-transform shrink-0", open && "rotate-180")}
        />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className={cn(
          "absolute right-0 top-full mt-1.5 z-50 w-72",
          "rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden",
        )}>
          {connections.length > 0 && (
            <>
              <div className="px-3 pt-3 pb-1">
                <p className="font-mono text-[10px] text-crema/25 uppercase tracking-widest">
                  Instancias guardadas
                </p>
              </div>
              <div className="py-1 max-h-52 overflow-y-auto">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className={cn(
                      "flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors group",
                      conn.id === activeId ? "bg-musgo/20" : "hover:bg-musgo/10"
                    )}
                    onClick={() => { setActive(conn.id); setOpen(false); }}
                  >
                    <div className="w-6 h-6 rounded-md bg-musgo/30 flex items-center justify-center shrink-0">
                      <Server size={11} className="text-crema/50" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-xs text-crema/70 truncate">{conn.label}</p>
                      <p className="font-mono text-[10px] text-crema/30 truncate">
                        {conn.authMode === "sql" ? conn.username : "Windows Auth"}
                        {conn.database !== "<default>" ? ` · ${conn.database}` : ""}
                      </p>
                    </div>
                    {conn.id === activeId && (
                      <Check size={13} className="text-green-400 shrink-0" />
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeConnection(conn.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-crema/25 hover:text-red-400 p-1 rounded shrink-0"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
              <div className="border-t border-musgo/15" />
            </>
          )}

          {/* New connection */}
          <button
            onClick={() => { setOpen(false); onNewConnection(); }}
            className="w-full flex items-center gap-2.5 px-3 py-3 text-left hover:bg-musgo/10 transition-colors"
          >
            <div className="w-6 h-6 rounded-md bg-arcilla/10 flex items-center justify-center shrink-0">
              <Plus size={11} className="text-arcilla" />
            </div>
            <span className="font-mono text-xs text-crema/50 hover:text-crema/70 transition-colors">
              Nueva conexión…
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
