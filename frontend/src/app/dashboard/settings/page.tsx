"use client";

import { useState } from "react";
import {
  BadgeCheck,
  Building2,
  HardDrive,
  LogOut,
  Mail,
  ServerCog,
  User,
  UsersRound,
} from "lucide-react";
import { AgentsAdmin } from "@/components/agents/agents-admin";
import { UsersAdmin } from "@/components/users/users-admin";
import { StoragePreferenceSettings } from "@/components/settings/storage-preference-settings";
import { useAuth } from "@/hooks/useAuth";
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  supervisor: "Supervisor",
  client: "Cliente",
};

function Row({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 border-b border-musgo/10 py-3 last:border-0">
      <Icon size={15} className="shrink-0 text-subtle" />
      <span className="w-28 shrink-0 font-sans text-xs uppercase tracking-wider text-muted">{label}</span>
      <span className="truncate text-sm text-crema">{value || "—"}</span>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-musgo/25 bg-surface p-5">
      <p className="mb-3 text-sm font-medium text-crema">{title}</p>
      {children}
    </div>
  );
}

type TabId = "perfil" | "usuarios" | "agentes" | "almacenamiento";

export default function SettingsPage() {
  const user = useAuthStore((state) => state.user);
  const { logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<TabId>("perfil");

  const tabs: { id: TabId; label: string; icon: React.ElementType; adminOnly?: boolean }[] = [
    { id: "perfil", label: "Perfil", icon: User },
    { id: "usuarios", label: "Usuarios", icon: UsersRound, adminOnly: true },
    { id: "agentes", label: "Agentes", icon: ServerCog, adminOnly: true },
    { id: "almacenamiento", label: "Almacenamiento", icon: HardDrive, adminOnly: true },
  ];
  const visibleTabs = tabs.filter((item) => !item.adminOnly || isAdmin);

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <p className="mb-1 font-sans text-xs uppercase tracking-[0.18em] text-arcilla">Cuenta</p>
        <h1 className="font-title text-[28px] font-semibold text-crema">
          Configuración
        </h1>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-musgo/15 pb-3" role="tablist" aria-label="Configuración">
        {visibleTabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "flex h-9 items-center gap-2 rounded-full border px-4 font-sans text-xs transition-colors",
              tab === item.id
                ? "border-arcilla/30 bg-arcilla/15 text-arcilla"
                : "border-transparent text-muted hover:bg-musgo/10 hover:text-crema",
            )}
          >
            <item.icon size={13} />
            {item.label}
          </button>
        ))}
      </div>

      {tab === "perfil" ? (
        <div className="max-w-3xl space-y-6">
          <Card title="Perfil">
            <Row icon={User} label="Nombre" value={user?.fullName ?? ""} />
            <Row icon={Mail} label="Correo" value={user?.email ?? ""} />
            <Row icon={BadgeCheck} label="Rol" value={user ? (ROLE_LABEL[user.role] ?? user.role) : ""} />
            <Row icon={Building2} label="Usuario" value={user?.username ?? ""} />
          </Card>

          <Card title="Sesión">
            <button
              type="button"
              onClick={logout}
              className="flex w-full items-center gap-3 rounded-[0.65rem] px-3 py-2.5 text-sm text-danger transition-colors hover:bg-danger/10 hover:text-danger"
            >
              <LogOut size={15} />
              Cerrar sesión
            </button>
          </Card>
        </div>
      ) : null}

      {tab === "usuarios" && isAdmin ? <UsersAdmin /> : null}

      {tab === "agentes" && isAdmin ? <AgentsAdmin /> : null}

      {tab === "almacenamiento" && isAdmin ? <StoragePreferenceSettings /> : null}
    </div>
  );
}
