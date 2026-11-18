"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, SURFACE } from "@/components/ui/page-header";
import { BackupList } from "@/components/backups/backup-list";
import { AgentTriggerBackupModal } from "@/components/backups/agent-trigger-backup-modal";
import { AgentSelector } from "@/components/agents/agent-selector";
import { useBackupList } from "@/hooks/useBackups";
import { BackupAutomationList, BackupAutomationModal } from "@/components/backups/backup-automation";
import { useAgents, useSelectedAgentId } from "@/hooks/useAgents";
import { cn, isAgentModuleDisabled } from "@/lib/utils";

function BackupStats() {
  const { data } = useBackupList(0, 100);

  const stats = [
    { label: "Total",        value: data?.total ?? 0,                                                                   tone: "text-crema" },
    { label: "Completados",  value: data?.items.filter((b) => b.status === "completed").length ?? 0,                     tone: "text-crema" },
    { label: "En ejecución", value: data?.items.filter((b) => b.status === "running" || b.status === "pending").length ?? 0, tone: "text-arcilla" },
    { label: "Fallidos",     value: data?.items.filter((b) => b.status === "failed").length ?? 0,                        tone: "text-red-300" },
  ];

  return (
    <section aria-label="Resumen de backups" className="overflow-hidden rounded-[0.9rem] border border-crema/[0.07]">
      <dl className="grid grid-cols-2 gap-px bg-crema/[0.07] lg:grid-cols-4">
        {stats.map(({ label, value, tone }) => (
          <div key={label} className="flex flex-col gap-1 bg-carbon px-4 py-3.5 sm:px-5">
            <dt className="text-sm text-crema/65">{label}</dt>
            <dd className={cn("text-2xl font-semibold leading-none tracking-[-0.02em] tabular-nums", value > 0 ? tone : "text-crema")}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function BackupsPage() {
  const [backupModalOpen, setBackupModalOpen] = useState(false);
  const [automationModalOpen, setAutomationModalOpen] = useState(false);
  const agentsQuery = useAgents();
  const agents = agentsQuery.data?.items ?? [];
  const [agentId, setAgentId] = useSelectedAgentId(agents);
  const agentModuleOff = isAgentModuleDisabled(agentsQuery.error);

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader
        title="Backups"
        description="Respaldos de SQL Server ejecutados por los agentes Windows: historial, planes automáticos y ejecución manual."
        actions={
          <>
            {!agentModuleOff ? <AgentSelector agents={agents} value={agentId} onChange={setAgentId} /> : null}
            <Button
              onClick={() => setBackupModalOpen(true)}
              disabled={!agentId}
              title={agentModuleOff ? "Requiere el módulo de agentes" : !agentId ? "Selecciona un agente conectado" : undefined}
              className="gap-2"
            >
              <Plus size={15} />
              Nuevo backup
            </Button>
          </>
        }
      />

      {agentModuleOff ? (
        <p className="rounded-[0.8rem] border border-arcilla/25 bg-arcilla/[0.06] px-4 py-3 text-sm text-crema/80">
          <span className="font-medium text-crema">Módulo de agentes desactivado.</span>{" "}
          Puedes consultar el historial, pero para lanzar o programar backups un administrador debe activar
          el agente Windows en el servidor.
        </p>
      ) : null}

      <BackupStats />

      <BackupAutomationList onNew={() => setAutomationModalOpen(true)} />

      <section className={cn(SURFACE, "overflow-hidden")}>
        <BackupList />
      </section>

      <AgentTriggerBackupModal open={backupModalOpen} onClose={() => setBackupModalOpen(false)} agentId={agentId} />
      <BackupAutomationModal open={automationModalOpen} onClose={() => setAutomationModalOpen(false)} />
    </div>
  );
}
