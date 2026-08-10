import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SqlConnection, ConnectionPayload } from "@/types/connection";

interface ConnectionsState {
  connections: SqlConnection[];
  activeId:    string | null;

  addConnection:    (conn: SqlConnection) => void;
  updateConnection: (id: string, patch: Partial<SqlConnection>) => void;
  removeConnection: (id: string) => void;
  setActive:        (id: string | null) => void;
  getActive:        () => SqlConnection | null;
  toPayload:        (conn: SqlConnection) => ConnectionPayload;
}

export const useConnectionsStore = create<ConnectionsState>()(
  persist(
    (set, get) => ({
      connections: [],
      activeId:    null,

      addConnection: (conn) =>
        set((s) => ({
          connections: [...s.connections, conn],
          activeId:    conn.id,
        })),

      updateConnection: (id, patch) =>
        set((s) => ({
          connections: s.connections.map((c) => (c.id === id ? { ...c, ...patch } : c)),
        })),

      removeConnection: (id) =>
        set((s) => {
          const remaining = s.connections.filter((c) => c.id !== id);
          return {
            connections: remaining,
            activeId:
              s.activeId === id
                ? (remaining[0]?.id ?? null)
                : s.activeId,
          };
        }),

      setActive: (id) => set({ activeId: id }),

      getActive: () => {
        const { connections, activeId } = get();
        return connections.find((c) => c.id === activeId) ?? null;
      },

      toPayload: (conn): ConnectionPayload => ({
        server:     conn.server,
        username:   conn.authMode === "windows" ? "" : conn.username,
        password:   conn.authMode === "windows" ? "" : conn.password,
        database:   conn.database === "<default>" ? undefined : conn.database,
        encrypt:    conn.encrypt.toLowerCase(),
        trust_cert: conn.trustServerCertificate,
      }),
    }),
    {
      name: "infra-sql-connections",
      // Seguridad: NUNCA persistir contraseñas en localStorage (legible por cualquier
      // script / XSS). Se guarda la conexión sin password; el usuario la reintroduce
      // en la sesión. El password vive solo en memoria mientras la pestaña está abierta.
      partialize: (s) => ({
        connections: s.connections.map((c) => ({ ...c, password: "" })),
        activeId:    s.activeId,
      }),
    }
  )
);
