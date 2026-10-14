"use client";

import { useState } from "react";
import { Check, Copy, Loader2, RefreshCw, X } from "lucide-react";
import {
  useAgentReplacement,
  useCancelAgentReplacement,
  useConfirmAgentReplacement,
  useCreateAgentReplacement,
} from "@/hooks/useAgents";
import type { AgentRecord } from "@/types/agent";


export function AgentReplacementDialog({ agent, onClose }: { agent: AgentRecord; onClose: () => void }) {
  const create = useCreateAgentReplacement();
  const confirm = useConfirmAgentReplacement();
  const cancel = useCancelAgentReplacement();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const session = useAgentReplacement(sessionId);
  const current = session.data ?? create.data;
  const busy = create.isPending || confirm.isPending || cancel.isPending;

  async function start() {
    const result = await create.mutateAsync(agent.id);
    setSessionId(result.id);
    setPairingCode(result.code ?? null);
  }

  async function cancelSession() {
    if (!sessionId) return onClose();
    await cancel.mutateAsync(sessionId);
  }

  return (
    <div className="!m-0 fixed inset-0 z-[95] grid place-items-center bg-black/70 p-4">
      <section className="w-full max-w-4xl overflow-hidden rounded-[0.75rem] border border-musgo/30 bg-carbon">
        <header className="flex items-start justify-between border-b border-musgo/20 px-6 py-5">
          <div><p className="text-xs uppercase tracking-[0.16em] text-arcilla">Cambio de infraestructura</p><h2 className="mt-1 text-xl font-medium text-crema">Reemplazar {agent.hostname}</h2><p className="mt-1 text-xs text-muted">El servidor actual continuará operando hasta que compare y confirme el cambio.</p></div>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="text-subtle hover:text-crema"><X size={17} /></button>
        </header>

        <div className="min-h-72 p-6">
          {!current ? (
            <div className="max-w-xl space-y-4">
              <p className="text-sm leading-relaxed text-muted">Genere un código temporal, ejecute el instalador universal en el servidor nuevo y espere a que aparezca aquí. Nada se moverá todavía.</p>
              <button type="button" onClick={start} disabled={busy} className="flex h-10 items-center gap-2 rounded-[0.5rem] bg-arcilla px-4 text-xs font-medium text-carbon disabled:opacity-40">{create.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Generar código de reemplazo</button>
            </div>
          ) : (
            <div className="space-y-5">
              {pairingCode && current.status === "awaiting_candidate" ? <div className="flex flex-wrap items-center justify-between gap-3 border-b border-musgo/20 pb-5"><div><p className="text-xs text-muted">Código para el instalador del servidor nuevo</p><p className="mt-1 font-sans text-lg tracking-[0.12em] text-crema">{pairingCode}</p><p className="mt-1 text-xs text-subtle">Vence {new Date(current.expiresAt).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}</p></div><button type="button" onClick={() => navigator.clipboard.writeText(pairingCode)} className="flex items-center gap-2 text-xs text-arcilla"><Copy size={13} /> Copiar</button></div> : null}

              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] border-collapse text-left text-xs">
                  <thead><tr className="border-b border-musgo/25 text-subtle"><th className="py-2 font-normal">Comparación</th><th className="py-2 font-normal">Servidor actual</th><th className="py-2 font-normal">Servidor candidato</th></tr></thead>
                  <tbody className="text-muted">
                    <tr className="border-b border-musgo/15"><td className="py-3 text-subtle">Nombre</td><td>{current.oldAgent.hostname}</td><td>{current.candidateAgent?.hostname ?? "Esperando conexión…"}</td></tr>
                    <tr className="border-b border-musgo/15"><td className="py-3 text-subtle">Versión</td><td>{current.oldAgent.agentVersion}</td><td>{current.candidateAgent?.agentVersion ?? "—"}</td></tr>
                    <tr className="border-b border-musgo/15"><td className="py-3 text-subtle">Salud</td><td>{current.oldAgent.healthStatus}</td><td>{current.candidateAgent?.healthStatus ?? "—"}</td></tr>
                    <tr className="border-b border-musgo/15"><td className="py-3 text-subtle">Volúmenes</td><td>{current.oldAgent.volumes.length}</td><td>{current.candidateAgent?.volumes.length ?? "—"}</td></tr>
                    <tr><td className="py-3 text-subtle">SQL detectado</td><td>{current.oldAgent.sqlCandidates.length}</td><td>{current.candidateAgent?.sqlCandidates.length ?? "—"}</td></tr>
                  </tbody>
                </table>
              </div>

              {current.profilesRequiringSecret.length ? <div className="border-l-2 border-amber-400/50 pl-3"><p className="text-xs text-warning">{current.profilesRequiringSecret.length} conexión(es) requerirán volver a capturar su secreto en el servidor nuevo.</p><p className="mt-1 text-xs text-subtle">Las rutas, horarios e historial sí se conservarán.</p></div> : null}
              {current.blockers.length ? <div><p className="text-xs text-muted">Antes de confirmar:</p><ul className="mt-2 space-y-1 text-xs text-warning">{current.blockers.map((blocker) => <li key={blocker}>• {blocker}</li>)}</ul></div> : null}
              {current.status === "completed" ? <p className="flex items-center gap-2 text-sm text-success"><Check size={15} /> Reemplazo confirmado. El agente anterior quedó revocado.</p> : null}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between border-t border-musgo/20 px-6 py-4">
          <button type="button" onClick={cancelSession} disabled={busy || current?.status === "completed"} className="text-xs text-muted disabled:opacity-25">{sessionId ? "Cancelar reemplazo" : "Cerrar"}</button>
          {sessionId && current?.status === "awaiting_confirmation" ? <button type="button" onClick={() => confirm.mutate(sessionId)} disabled={!current.canConfirm || busy} className="flex h-9 items-center gap-2 rounded-[0.5rem] bg-arcilla px-4 text-xs font-medium text-carbon disabled:opacity-30">{confirm.isPending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Confirmar traspaso</button> : null}
        </footer>
      </section>
    </div>
  );
}
