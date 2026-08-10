import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { FMConnection, FMProtocol, QuickRule } from "@/types/filemanager";

interface FMState {
  connections: FMConnection[];
  activeId:    string | null;
  quickRules:  QuickRule[];

  addConnection:    (c: Omit<FMConnection, "id" | "createdAt">) => FMConnection;
  removeConnection: (id: string) => void;
  setActive:        (id: string | null) => void;
  getActive:        () => FMConnection | null;
  toPayload:        (c: FMConnection) => Pick<FMConnection, "host" | "port" | "protocol" | "username" | "password" | "privateKey" | "passphrase">;

  addQuickRule:    (r: Omit<QuickRule, "id">) => void;
  removeQuickRule: (id: string) => void;
}

const DEFAULT_RULES: QuickRule[] = [
  { id: "r1", label: "Limpiar Core\\Respuesta",  path: "Core\\Respuesta",  type: "contents" },
  { id: "r2", label: "Limpiar Core\\log",         path: "Core\\log",         type: "contents" },
  { id: "r3", label: "Limpiar Core\\LogsRadian",  path: "Core\\LogsRadian",  type: "contents" },
  { id: "r4", label: "Eliminar BD_log.txt",        path: "",                  type: "pattern", pattern: "BD_log.txt" },
];

export const useFMStore = create<FMState>()(
  persist(
    (set, get) => ({
      connections: [],
      activeId:    null,
      quickRules:  DEFAULT_RULES,

      addConnection: (c) => {
        const conn: FMConnection = { ...c, id: crypto.randomUUID(), createdAt: new Date().toISOString() };
        set((s) => ({ connections: [...s.connections, conn] }));
        return conn;
      },
      removeConnection: (id) =>
        set((s) => ({
          connections: s.connections.filter((c) => c.id !== id),
          activeId:    s.activeId === id ? null : s.activeId,
        })),
      setActive: (id) => set({ activeId: id }),
      getActive: () => {
        const { connections, activeId } = get();
        return connections.find((c) => c.id === activeId) ?? null;
      },
      toPayload: (c) => ({
        host: c.host, port: c.port, protocol: c.protocol, username: c.username,
        password: c.password, privateKey: c.privateKey ?? "", passphrase: c.passphrase ?? "",
      }),

      addQuickRule: (r) =>
        set((s) => ({ quickRules: [...s.quickRules, { ...r, id: crypto.randomUUID() }] })),
      removeQuickRule: (id) =>
        set((s) => ({ quickRules: s.quickRules.filter((r) => r.id !== id) })),
    }),
    {
      name: "infra-fm-store",
      // Seguridad: NUNCA persistir contraseñas ni llaves privadas SFTP/FTP en
      // localStorage. Se conserva la conexión sin secretos; el usuario los reintroduce
      // al reconectar. Las reglas rápidas (quickRules) sí se persisten porque no
      // contienen secretos.
      partialize: (s) => ({
        connections: s.connections.map((c) => ({ ...c, password: "", privateKey: "", passphrase: "" })),
        activeId:    s.activeId,
        quickRules:  s.quickRules,
      }),
    }
  )
);
