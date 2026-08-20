"use client";

import { useState } from "react";
import { Database, CheckCircle2, XCircle, Clock, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BackupList } from "@/components/backups/backup-list";
import { AgentTriggerBackupModal } from "@/components/backups/agent-trigger-backup-modal";
import { AgentSelector } from "@/components/agents/agent-selector";
import { useBackupList } from "@/hooks/useBackups";
import { BackupAutomationList, BackupAutomationModal } from "@/components/backups/backup-automation";
import { useAgents, useSelectedAgentId } from "@/hooks/useAgents";

function BackupStats() {
  const { data } = useBackupList(0, 100);

  const stats = {
    total:     data?.total ?? 0,
    completed: data?.items.filter((b) => b.status === "completed").length ?? 0,
    running:   data?.items.filter((b) => b.status === "running" || b.status === "pending").length ?? 0,
    failed:    data?.items.filter((b) => b.status === "failed").length ?? 0,
  };

  const cards = [
    { label: "Total backups", value: stats.total,     icon: Database,      color: "text-crema/60",  bg: "bg-musgo/30" },
    { label: "Completados",   value: stats.completed, icon: CheckCircle2,  color: "text-green-400", bg: "bg-green-900/20" },
    { label: "En ejecución",  value: stats.running,   icon: Clock,         color: "text-arcilla",   bg: "bg-arcilla/10" },
    { label: "Fallidos",      value: stats.failed,    icon: XCircle,       color: "text-red-400",   bg: "bg-red-900/20" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map(({ label, value, icon: Icon, color, bg }) => (
        <div
          key={label}
          className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-4 hover:border-musgo/30 transition-colors"
        >
          <div className={`w-8 h-8 rounded-[0.65rem] ${bg} flex items-center justify-center mb-3`}>
            <Icon size={15} className={color} />
          </div>
          <p className="text-3xl font-semibold tabular-nums text-crema/90">{value}</p>
          <p className="font-mono text-[11px] text-crema/35 mt-0.5">{label}</p>
        </div>
      ))}
    </div>
  );
}

export default function BackupsPage() {
  const [backupModalOpen, setBackupModalOpen] = useState(false);
  const [automationModalOpen, setAutomationModalOpen] = useState(false);
  const agentsQuery = useAgents();
  const agents = agentsQuery.data?.items ?? [];
  const [agentId, setAgentId] = useSelectedAgentId(agents);

  return (
    <div className="space-y-7">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Módulo</p>
          <h1 className="font-title text-4xl font-semibold text-crema">
            Backups<span className="text-arcilla">.</span>
          </h1>
        </div>

        <div className="flex items-center gap-2 mt-1 flex-wrap justify-end">
          <AgentSelector agents={agents} value={agentId} onChange={setAgentId} />

          {/* Trigger backup */}
          <Button onClick={() => setBackupModalOpen(true)} disabled={!agentId} className="gap-2">
            <Plus size={14} />
            Nuevo Backup
          </Button>
        </div>
      </div>

      {/* Stats */}
      <BackupStats />

      <BackupAutomationList onNew={() => setAutomationModalOpen(true)} />

      {/* Historial */}
      <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 overflow-hidden">
        <BackupList />
      </div>

      {/* Modals */}
      <AgentTriggerBackupModal open={backupModalOpen} onClose={() => setBackupModalOpen(false)} agentId={agentId} />
      <BackupAutomationModal open={automationModalOpen} onClose={() => setAutomationModalOpen(false)} />
    </div>
  );
}
