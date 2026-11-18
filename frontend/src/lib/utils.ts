import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/** Código de error de la API (`{ error: { code } }`) a partir de un error de Axios. */
export function apiErrorCode(error: unknown): string | undefined {
  const data = (error as { response?: { data?: { error?: { code?: string } } } } | null)?.response?.data;
  return data?.error?.code;
}

/** El backend responde 503 AGENT_MODULE_DISABLED cuando el módulo de agentes Windows está apagado. */
export function isAgentModuleDisabled(error: unknown): boolean {
  return apiErrorCode(error) === "AGENT_MODULE_DISABLED";
}
