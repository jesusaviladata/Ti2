"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, ShieldCheck, X } from "lucide-react";
import { useAgentJob, useSaveAgentConfiguration, useValidateAgentRoot } from "@/hooks/useAgents";
import type { AgentRecord } from "@/types/agent";

export function AgentRootWizard({ agent, onClose }: { agent: AgentRecord; onClose: () => void }) {
  const [name, setName] = useState(agent.configuration?.name ?? agent.hostname);
  const [root, setRoot] = useState(agent.configuration?.root ?? "D:\\Ipsofactu");
  const [validationJobId, setValidationJobId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const validate = useValidateAgentRoot();
  const save = useSaveAgentConfiguration();
  const validation = useAgentJob<{ valid?: boolean; propertiesDetected?: number }>(validationJobId);
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
            <div className="flex items-center gap-2 text-sm text-crema/65"><ShieldCheck size={14} className="text-arcilla" /> Alcance fijo de Ipsofactu</div>
            <p className="mt-1.5 font-mono text-[10px] leading-relaxed text-crema/35">Propiedad\core\Log · LogSec · LogsRadian · Respuesta · BD_log.txt</p>
          </div>

          {localError ? <p className="text-xs text-red-400">{localError}</p> : null}
          {validation.data?.status === "failed" ? <p className="text-xs text-red-400">{validation.data.error ?? "La raíz no superó la validación."}</p> : null}
          {validated ? (
            <p className="flex items-center gap-2 text-xs text-green-400"><CheckCircle2 size={14} /> Raíz validada · {validation.data?.result?.propertiesDetected ?? 0} propiedades detectadas</p>
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
