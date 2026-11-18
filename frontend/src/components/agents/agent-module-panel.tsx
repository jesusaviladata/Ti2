"use client";

import { useState } from "react";
import { Download, ShieldAlert } from "lucide-react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAgentModule, useDownloadBootstrap, useSetAgentModule } from "@/hooks/useAgentModule";
import { apiErrorCode, cn } from "@/lib/utils";
import type { AgentModuleStatus } from "@/types/agent";

const ERROR_TEXT: Record<string, string> = {
  AGENT_MODULE_SERVER_MANAGED: "La configuración del servidor fija este módulo; no se puede cambiar desde el panel.",
  AGENT_MODULE_SELF_SERVICE_DISABLED: "Este servidor no permite activar el módulo desde el panel.",
  AGENT_SIGNING_KEY_UNREADABLE:
    "La llave de firma guardada no se puede leer. Suele pasar cuando se cambia SECRET_KEY en el servidor.",
  AGENT_CONTROL_PLANE_INSECURE:
    "Los agentes solo se conectan por HTTPS y este servidor no tiene configurada una dirección HTTPS.",
};

function errorText(error: unknown, fallback: string) {
  const code = apiErrorCode(error);
  return (code && ERROR_TEXT[code]) || fallback;
}

function describe(state: AgentModuleStatus) {
  if (state.managedBy === "server") {
    return "Lo fija la configuración del servidor, así que no se puede cambiar desde aquí.";
  }
  if (state.managedBy === "locked") {
    return "La configuración de este servidor no permite activarlo desde el panel.";
  }
  if (state.enabled) {
    return "Los agentes Windows pueden vincularse y recibir órdenes firmadas por este servidor.";
  }
  if (!state.canManage) {
    return "Está desactivado. Pide a un administrador que lo active en Configuración → Agentes.";
  }
  return "Actívalo para vincular agentes Windows que ejecuten backups y limpieza en tus servidores. La primera vez se genera la llave con la que este servidor firma las órdenes.";
}

export function AgentModulePanel() {
  const status = useAgentModule();
  const toggle = useSetAgentModule();
  const download = useDownloadBootstrap();
  const [confirmOff, setConfirmOff] = useState(false);

  if (status.isLoading) {
    return (
      <section className="rounded-[1rem] border border-musgo/20 bg-musgo/[0.05] p-5">
        <p className="text-sm text-crema/55" role="status">Consultando el módulo de agentes…</p>
      </section>
    );
  }

  if (status.isError || !status.data) {
    return (
      <section className="rounded-[1rem] border border-red-400/25 p-5" role="alert">
        <p className="text-sm text-red-300">No se pudo consultar el estado del módulo de agentes.</p>
      </section>
    );
  }

  const state = status.data;

  return (
    <section className="rounded-[1rem] border border-musgo/20 bg-musgo/[0.05] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="agent-module-title" className="text-[15px] font-semibold text-crema">Módulo de agentes</h2>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11px]",
                state.enabled ? "bg-green-400/10 text-green-300" : "bg-crema/[0.06] text-crema/60",
              )}
            >
              {state.enabled ? "Activo" : "Inactivo"}
            </span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-crema/60">{describe(state)}</p>
        </div>

        {state.canManage ? (
          <button
            type="button"
            role="switch"
            aria-checked={state.enabled}
            aria-labelledby="agent-module-title"
            disabled={toggle.isPending}
            onClick={() => (state.enabled ? setConfirmOff(true) : toggle.mutate(true))}
            className={cn(
              "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors duration-200 ease-out-strong disabled:cursor-wait disabled:opacity-60",
              state.enabled ? "border-arcilla bg-arcilla" : "border-crema/20 bg-crema/10",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "inline-block h-4 w-4 rounded-full bg-crema shadow transition-transform duration-200 ease-out-strong",
                state.enabled ? "translate-x-[22px]" : "translate-x-[3px]",
              )}
            />
          </button>
        ) : null}
      </div>

      {toggle.isError ? (
        <p className="mt-4 rounded-[0.7rem] border border-red-400/25 px-4 py-3 text-sm text-red-300" role="alert">
          {errorText(toggle.error, "No se pudo cambiar el estado del módulo. Vuelve a intentarlo en unos segundos.")}
        </p>
      ) : null}

      {state.keyStatus === "unreadable" ? (
        <p className="mt-4 flex gap-2 rounded-[0.7rem] border border-red-400/25 px-4 py-3 text-sm text-red-300" role="alert">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" />
          {ERROR_TEXT.AGENT_SIGNING_KEY_UNREADABLE} Mientras tanto el módulo permanece apagado.
        </p>
      ) : null}

      {state.enabled ? (
        <div className="mt-5 space-y-4 border-t border-musgo/15 pt-4">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs text-crema/50">Dirección que usan los agentes</dt>
              <dd className="mt-1 truncate font-mono text-[13px] text-crema/85" title={state.controlPlaneUrl}>
                {state.controlPlaneUrl}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-crema/50">Llave de firma</dt>
              <dd className="mt-1 font-mono text-[13px] text-crema/85">
                {state.keyId}
                <span className="ml-2 font-sans text-xs text-crema/50">
                  {state.keySource === "environment" ? "de las variables de entorno" : "generada por este servidor"}
                </span>
              </dd>
            </div>
          </dl>

          {state.canManage ? (
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => download.mutate()}
                disabled={download.isPending}
                className="flex h-9 items-center gap-2 rounded-[0.625rem] border border-musgo/30 px-4 text-xs text-crema/75 hover:border-arcilla/40 hover:text-crema disabled:cursor-wait disabled:opacity-50"
              >
                <Download size={13} /> {download.isPending ? "Preparando…" : "Descargar bootstrap.json"}
              </button>
              <p className="max-w-xl text-xs leading-relaxed text-crema/50">
                Contiene la dirección y la llave pública de este servidor, nunca la privada. Se usa para armar el
                paquete del agente que se instala en cada servidor Windows.
              </p>
            </div>
          ) : null}

          {download.isError ? (
            <p className="rounded-[0.7rem] border border-red-400/25 px-4 py-3 text-sm text-red-300" role="alert">
              {errorText(download.error, "No se pudo descargar bootstrap.json. Vuelve a intentarlo.")}
            </p>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={confirmOff}
        title="¿Desactivar el módulo de agentes?"
        message="Los agentes dejarán de recibir órdenes y no se ejecutarán los backups programados por agente. Los agentes instalados siguen vinculados: al reactivarlo se reconectan solos en alrededor de un minuto, sin reinstalar."
        confirmLabel="Desactivar"
        danger
        onConfirm={() => {
          setConfirmOff(false);
          toggle.mutate(false);
        }}
        onCancel={() => setConfirmOff(false)}
      />
    </section>
  );
}
