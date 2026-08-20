"use client";

import { useState } from "react";
import { Check, ChevronDown, Server, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentRecord } from "@/types/agent";

export function AgentSelector({
  agents,
  value,
  onChange,
}: {
  agents: AgentRecord[];
  value: string | null;
  onChange: (agentId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const online = agents.filter((agent) => agent.online);
  const selected = agents.find((agent) => agent.id === value) ?? null;

  if (!online.length) {
    return (
      <div className="flex h-9 items-center gap-2 rounded-[0.625rem] border border-musgo/20 bg-musgo/5 px-3 font-mono text-[11px] text-crema/30">
        <WifiOff size={13} /> Sin agentes conectados
      </div>
    );
  }

  if (online.length === 1) {
    return (
      <div className="flex h-9 items-center gap-2 rounded-[0.625rem] border border-green-500/20 bg-green-500/[0.06] px-3">
        <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
        <span className="font-mono text-[11px] text-crema/65">{online[0].hostname}</span>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex h-9 min-w-52 items-center justify-between gap-3 rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-left transition-colors hover:border-arcilla/35"
      >
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
          <span className="font-mono text-[11px] text-crema/65">{selected?.hostname ?? "Seleccionar agente"}</span>
        </span>
        <ChevronDown size={13} className={cn("text-crema/30 transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div role="listbox" className="absolute right-0 top-11 z-30 min-w-full overflow-hidden rounded-[0.75rem] border border-musgo/30 bg-carbon p-1 shadow-2xl">
          {online.map((agent) => (
            <button
              type="button"
              role="option"
              aria-selected={agent.id === value}
              key={agent.id}
              onClick={() => { onChange(agent.id); setOpen(false); }}
              className="flex w-full items-center justify-between gap-3 rounded-[0.5rem] px-3 py-2 text-left hover:bg-musgo/15"
            >
              <span className="flex items-center gap-2 font-mono text-[11px] text-crema/65">
                <Server size={12} className="text-arcilla/70" /> {agent.hostname}
              </span>
              {agent.id === value ? <Check size={12} className="text-arcilla" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
