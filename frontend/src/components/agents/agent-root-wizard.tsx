"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, ShieldCheck, X } from "lucide-react";
import { useAgentJob, useSaveAgentConfiguration, useValidateAgentRoot } from "@/hooks/useAgents";
import type { AgentRecord } from "@/types/agent";

export function AgentRootWizard({ agent, onClose }: { agent: AgentRecord; onClose: () => void }) {
  const [name, setName] = useState(agent.configuration?.name ?? agent.hostname);
  const [root, setRoot] = useState(agent.configuration?.root ?? "D:\\Ipsofactu");
  const [validationJobId, setValidationJobId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const validate = useValidateAgentRoot();
  const save = useSaveAgentConfiguration();
  const validation = useAgentJob<{
    valid?: boolean;
    propertiesDetected?: number;
    properties?: { path: string; depth: number; targetsFound: number }[];
    propertiesListTruncated?: boolean;
    scannedFolders?: number;
    maxDepth?: number;
    truncated?: boolean;
    errorCount?: number;
  }>(validationJobId);
  const report = validation.data?.status === "completed" ? validation.data.result : null;
  const validated = validation.data?.status === "completed" && validation.data.result?.valid === true;

  useEffect(() => {
    setValidationJobId(null);
    setLocalError(null);
  }, [root]);

  async function startValidation() {
    setLocalError(null);
    try {
      const result = await validate.mutateAsync({ agentId: agent.id, root: root.trim() });
      setValidationJobId(result.jobId);
    } catch (error) {
      const value = error as { response?: { data?: { error?: { message?: string } } } };
      setLocalError(value.response?.data?.error?.message ?? "No fue posible validar la raíz.");
    }
  }

  async function saveRoot() {
    if (!validationJobId || !validated) return;
    setLocalError(null);
    try {
      await save.mutateAsync({
        agentId: agent.id,
        name: name.trim(),
        root: root.trim(),
        validationJobId,
        serverId: agent.configuration?.id,
      });
      onClose();
    } catch (error) {
      const value = error as { response?: { data?: { error?: { message?: string } } } };
      setLocalError(value.response?.data?.error?.message ?? "No fue posible guardar la configuración.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <button type="button" aria-label="Cerrar" className="absolute inset-0 bg-carbon/85 backdrop-blur-sm" onClick={onClose} />
      <section className="relative w-full max-w-xl rounded-[1.25rem] border border-musgo/30 bg-carbon p-6">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-arcilla">Configuración obligatoria</p>
            <h2 className="text-xl font-medium text-crema">Raíz protegida del agente</h2>
          </div>
          <button type="button" onClick={onClose} className="text-crema/30 hover:text-crema"><X size={17} /></button>
        </div>

        <div className="space-y-4">
          <label className="block space-y-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-crema/40">Nombre operativo</span>
            <input value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 text-sm text-crema/80 outline-none focus:border-arcilla/45" />
          </label>
          <label className="block space-y-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-crema/40">Raíz única</span>
            <input value={root} onChange={(event) => setRoot(event.target.value)} className="h-10 w-full rounded-[0.625rem] border border-musgo/25 bg-musgo/10 px-3 font-mono text-xs text-crema/80 outline-none focus:border-arcilla/45" />
          </label>

          <div className="rounded-[0.75rem] border border-musgo/20 bg-musgo/[0.06] p-3">
            <div className="flex items-center gap-2 text-sm text-crema/75"><ShieldCheck size={14} className="text-arcilla" /> Alcance fijo de Ipsofactu</div>
            <p className="mt-1.5 text-xs leading-relaxed text-crema/55">
              La raíz puede ser una unidad completa (por ejemplo <span className="font-mono">D:\</span>). El agente busca hasta 8 niveles hacia abajo
              y solo toma como propiedad una carpeta cuyo <span className="font-mono">core</span> tenga la firma de Ipsofactu
              (al menos dos de: Log, LogSec, LogsRadian, Respuesta, BD_log.txt).
            </p>
          </div>

          {localError ? <p className="text-xs text-red-400">{localError}</p> : null}
          {validation.data?.status === "failed" ? <p className="text-xs text-red-400">{validation.data.error ?? "La raíz no superó la validación."}</p> : null}
          {report && !report.valid ? (
            <p className="flex items-start gap-2 text-xs text-amber-300"><AlertTriangle size={14} className="mt-px shrink-0" /> No se encontró ninguna propiedad con la firma de Ipsofactu bajo esta raíz ({report.scannedFolders ?? 0} carpetas revisadas).</p>
          ) : null}
          {validated && report ? (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-xs text-green-400">
                <CheckCircle2 size={14} /> Raíz validada · {report.propertiesDetected ?? 0} propiedades · {report.scannedFolders ?? 0} carpetas revisadas · hasta {report.maxDepth ?? 0} niveles
              </p>
              {report.truncated ? (
                <p className="flex items-start gap-2 text-xs text-amber-300"><AlertTriangle size={14} className="mt-px shrink-0" /> La búsqueda llegó a su límite de tiempo o de carpetas; puede haber propiedades sin listar. Considere una raíz más concreta.</p>
              ) : null}
              {report.errorCount ? <p className="text-xs text-amber-300">{report.errorCount} carpetas sin acceso para el agente (revise permisos de NETWORK SERVICE).</p> : null}
              <div className="max-h-48 overflow-y-auto rounded-[0.6rem] border border-crema/[0.08]">
                <ul className="divide-y divide-crema/[0.05] text-xs">
                  {(report.properties ?? []).map((item) => (
                    <li key={item.path} className="flex items-center justify-between gap-3 px-3 py-1.5">
                      <span className="min-w-0 truncate font-mono text-crema/80" title={item.path}>{item.path}</span>
                      <span className="shrink-0 tabular-nums text-crema/50">{item.targetsFound} objetivos</span>
                    </li>
                  ))}
                </ul>
              </div>
              {report.propertiesListTruncated ? <p className="text-xs text-crema/50">Se muestran las primeras {report.properties?.length ?? 0}.</p> : null}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={startValidation} disabled={!root.trim() || validate.isPending || Boolean(validationJobId && !validation.data)} className="h-9 rounded-[0.625rem] border border-arcilla/30 bg-arcilla/10 px-4 text-xs text-arcilla disabled:opacity-40">
              {validate.isPending || (validationJobId && !validation.data) ? <span className="flex items-center gap-2"><Loader2 size={13} className="animate-spin" /> Validando</span> : "Validar raíz"}
            </button>
            <button type="button" onClick={saveRoot} disabled={!validated || save.isPending || !name.trim()} className="h-9 rounded-[0.625rem] bg-arcilla px-4 text-xs font-medium text-carbon disabled:opacity-35">
              {save.isPending ? "Guardando…" : "Guardar configuración"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
