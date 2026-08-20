"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, CheckCircle2, Database, Loader2, PackageCheck, Search, Send, X, XCircle } from "lucide-react";
import { useAgentJob, useAgentProfiles } from "@/hooks/useAgents";
import { useBackupStatus, useTriggerAgentBackup } from "@/hooks/useBackups";
import { agentsService } from "@/services/agents.service";
import { formatBytes } from "@/lib/utils";
import type { BackupRecord, BackupType } from "@/types/backup";

interface Props { open: boolean; onClose: () => void; agentId: string | null }

function errorMessage(error: unknown) {
  const value = error as { response?: { data?: { detail?: string | { message?: string }; error?: { message?: string } } } };
  const detail = value.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.message ?? value.response?.data?.error?.message ?? "No fue posible iniciar el backup.";
}

function BackupRunRow({ initial }: { initial: BackupRecord }) {
  const status = useBackupStatus(initial.id).data ?? initial;
  const ready = status.status === "completed";
  const failed = status.status === "failed";
  const progress = failed ? 100 : status.progressPercent ?? 0;
  const delivery = status.deliveryStatus ?? "pending";
  return (
    <div className="rounded-[0.875rem] border border-musgo/20 bg-musgo/[0.05] p-3.5">
      <div className="flex items-center justify-between gap-3">
        <span className="truncate font-mono text-xs text-crema/75">{status.databaseName}</span>
        {ready ? <CheckCircle2 size={14} className="text-green-400" /> : failed ? <XCircle size={14} className="text-red-400" /> : <Loader2 size={14} className="animate-spin text-arcilla" />}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-musgo/20"><div style={{ width: `${progress}%` }} className={failed ? "h-full bg-red-500 transition-[width]" : ready ? "h-full bg-green-500 transition-[width]" : "h-full bg-arcilla transition-[width]"} /></div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px]">
        <span className={failed ? "text-red-400" : ready ? "text-green-400" : "text-arcilla"}>
          {failed ? "Backup fallido" : ready ? ".BAK creado y validado" : status.phase === "validating_bak" ? "Validando con RESTORE VERIFYONLY" : "Creando .BAK"}
        </span>
        {status.fileSizeBytes ? <span className="text-crema/35">{formatBytes(status.fileSizeBytes)}</span> : null}
      </div>
      {ready ? (
        <div className="mt-2 flex items-center gap-2 border-t border-musgo/15 pt-2 text-[10px]">
          {delivery === "delivered" || delivery === "local_ready" ? <PackageCheck size={12} className="text-green-400" /> : delivery === "failed" ? <XCircle size={12} className="text-amber-400" /> : <Send size={12} className="text-arcilla" />}
          <span className={delivery === "failed" ? "text-amber-400" : delivery === "delivered" || delivery === "local_ready" ? "text-green-400/80" : "text-crema/40"}>
            {delivery === "delivered" ? "Entregado y verificado" : delivery === "local_ready" ? "ZIP local listo" : delivery === "failed" ? `Backup listo · entrega fallida${status.deliveryErrorMessage ? `: ${status.deliveryErrorMessage}` : ""}` : status.deliveryPhase === "transferring" ? "Enviando en segundo plano…" : "Preparando ZIP en segundo plano…"}
          </span>
        </div>
      ) : null}
    </div>
  );
}

export function AgentTriggerBackupModal({ open, onClose, agentId }: Props) {
  const profiles = useAgentProfiles(open ? agentId : null);
  const trigger = useTriggerAgentBackup();
  const [sqlProfileId, setSqlProfileId] = useState("");
  const [destinationProfileId, setDestinationProfileId] = useState("");
  const [backupType, setBackupType] = useState<BackupType>("full");
  const [catalogJobId, setCatalogJobId] = useState<string | null>(null);
  const catalog = useAgentJob<{ databases: string[] }>(catalogJobId);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [records, setRecords] = useState<BackupRecord[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    const first = profiles.data?.sqlInstances[0]?.id ?? "";
    if (!profiles.data?.sqlInstances.some((item) => item.id === sqlProfileId)) setSqlProfileId(first);
  }, [profiles.data, sqlProfileId]);

  useEffect(() => {
    setCatalogJobId(null); setSelected([]); setRecords([]); setLocalError(null);
  }, [agentId, sqlProfileId]);

  const databases = catalog.data?.status === "completed" ? catalog.data.result?.databases ?? [] : [];
  const filtered = useMemo(() => databases.filter((name) => name.toLowerCase().includes(search.toLowerCase())), [databases, search]);

  if (!open) return null;

  async function loadDatabases() {
    if (!agentId || !sqlProfileId) return;
    setLocalError(null);
    try { setCatalogJobId((await agentsService.createDatabaseCatalog(agentId, sqlProfileId)).jobId); }
    catch (error) { setLocalError(errorMessage(error)); }
  }

  async function submit() {
    if (!agentId || !sqlProfileId || !selected.length) return;
    setLocalError(null);
    try {
      const result = await trigger.mutateAsync({ agentId, sqlProfileId, databaseNames: selected, backupType, destinationProfileId: destinationProfileId || undefined });
      setRecords(result.backups);
    } catch (error) { setLocalError(errorMessage(error)); }
  }

  function close() {
    setCatalogJobId(null); setSelected([]); setRecords([]); setSearch(""); trigger.reset(); onClose();
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <button type="button" aria-label="Cerrar" className="absolute inset-0 bg-carbon/85 backdrop-blur-sm" onClick={close} />
      <section className="relative flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-[1.25rem] border border-musgo/30 bg-carbon">
        <header className="flex items-start justify-between border-b border-musgo/20 px-6 py-5">
          <div><p className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-arcilla">Agente del servidor</p><h2 className="text-xl font-medium text-crema">Nuevo backup</h2></div>
          <button type="button" onClick={close} className="text-crema/30 hover:text-crema"><X size={17} /></button>
        </header>
        <div className="overflow-y-auto p-6">
          {records.length ? (
            <div className="space-y-3">
              <div className="rounded-[0.75rem] border border-arcilla/20 bg-arcilla/[0.05] p-3 text-xs leading-relaxed text-crema/45">La barra principal termina al crear y validar el .BAK. El ZIP y el envío continúan como un estado separado.</div>
              {records.map((record) => <BackupRunRow key={record.id} initial={record} />)}
              <button type="button" onClick={close} className="mt-2 h-10 w-full rounded-[0.625rem] border border-musgo/25 text-xs text-crema/55">Cerrar · el proceso continúa en segundo plano</button>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5"><span className="text-[10px] uppercase tracking-wider text-crema/35">Instancia SQL</span><select value={sqlProfileId} onChange={(event) => setSqlProfileId(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-xs text-crema/70 outline-none"><option value="">Seleccionar</option>{profiles.data?.sqlInstances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
                <label className="space-y-1.5"><span className="text-[10px] uppercase tracking-wider text-crema/35">Entrega</span><select value={destinationProfileId} onChange={(event) => setDestinationProfileId(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-xs text-crema/70 outline-none"><option value="">Sólo almacenamiento local</option>{profiles.data?.backupDestinations.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              </div>
              <div><p className="mb-2 text-[10px] uppercase tracking-wider text-crema/35">Tipo</p><div className="grid grid-cols-3 gap-2">{([['full','Full'],['differential','Diferencial'],['log','Log']] as const).map(([value,label]) => <button key={value} type="button" onClick={() => setBackupType(value)} className={backupType === value ? "h-9 rounded-[0.625rem] border border-arcilla/35 bg-arcilla/10 text-xs text-arcilla" : "h-9 rounded-[0.625rem] border border-musgo/20 text-xs text-crema/40"}>{label}</button>)}</div></div>
              <div>
                <div className="mb-2 flex items-center justify-between"><p className="text-[10px] uppercase tracking-wider text-crema/35">Bases de datos</p><button type="button" onClick={loadDatabases} disabled={!sqlProfileId || Boolean(catalogJobId && catalog.data && !["completed","failed","cancelled"].includes(catalog.data.status))} className="flex items-center gap-1.5 text-[10px] text-arcilla disabled:opacity-35">{catalogJobId && catalog.data?.status !== "completed" && catalog.data?.status !== "failed" ? <Loader2 size={11} className="animate-spin" /> : <Database size={11} />} Consultar agente</button></div>
                {databases.length ? <div className="overflow-hidden rounded-[0.75rem] border border-musgo/20"><div className="flex items-center gap-2 border-b border-musgo/15 px-3"><Search size={12} className="text-crema/25" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar…" className="h-9 flex-1 bg-transparent text-xs text-crema/65 outline-none" /></div><div className="max-h-48 overflow-y-auto p-1">{filtered.map((database) => { const checked = selected.includes(database); return <button type="button" key={database} onClick={() => setSelected(checked ? selected.filter((item) => item !== database) : [...selected, database])} className="flex w-full items-center gap-2 rounded-[0.5rem] px-3 py-2 text-left font-mono text-xs text-crema/60 hover:bg-musgo/10"><span className={checked ? "grid h-3.5 w-3.5 place-items-center rounded-sm bg-arcilla text-carbon" : "h-3.5 w-3.5 rounded-sm border border-musgo/35"}>{checked ? <Check size={9} /> : null}</span>{database}</button>; })}</div></div> : <div className="rounded-[0.75rem] border border-musgo/15 p-4 text-xs text-crema/30">Seleccione una instancia y consulte las bases del agente.</div>}
              </div>
              {catalog.data?.status === "failed" ? <p className="text-xs text-red-400">{catalog.data.error}</p> : null}
              {localError ? <p className="text-xs text-red-400">{localError}</p> : null}
              <button type="button" onClick={submit} disabled={!selected.length || trigger.isPending} className="flex h-10 w-full items-center justify-center gap-2 rounded-[0.625rem] bg-arcilla text-xs font-medium text-carbon disabled:opacity-35">{trigger.isPending ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />} Iniciar {selected.length > 1 ? `${selected.length} backups` : "backup"}</button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
