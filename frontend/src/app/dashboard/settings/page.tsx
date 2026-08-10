"use client";

import { useState } from "react";
import {
  User, Mail, BadgeCheck, Sun, Moon, LogOut,
  Building2, Server, Palette,
} from "lucide-react";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/components/providers/theme-provider";
import { CleanupServersAdmin } from "@/components/cleanup/server-admin";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<string, string> = {
  admin:      "Administrador",
  technician: "Técnico",
  supervisor: "Supervisor",
  client:     "Cliente",
};

function Row({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-musgo/10 last:border-0">
      <Icon size={15} className="text-crema/35 shrink-0" />
      <span className="font-mono text-[11px] text-crema/40 uppercase tracking-wider w-28 shrink-0">{label}</span>
      <span className="font-sans text-sm text-crema/80 truncate">{value || "—"}</span>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[1.25rem] bg-musgo/10 border border-musgo/20 p-5">
      <p className="font-sans text-sm font-medium text-crema/70 mb-3">{title}</p>
      {children}
    </div>
  );
}

type TabId = "perfil" | "servidores" | "apariencia";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const { logout } = useAuth();
  const { theme, toggle } = useTheme();
  const isAdmin = user?.role === "admin";

  const [tab, setTab] = useState<TabId>("perfil");

  const tabs: { id: TabId; label: string; icon: React.ElementType; adminOnly?: boolean }[] = [
    { id: "perfil",     label: "Perfil",     icon: User },
    { id: "servidores", label: "Servidores", icon: Server, adminOnly: true },
    { id: "apariencia", label: "Apariencia", icon: Palette },
  ];
  const visibleTabs = tabs.filter((t) => !t.adminOnly || isAdmin);

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <p className="font-mono text-xs text-arcilla uppercase tracking-[0.18em] mb-1">Cuenta</p>
        <h1 className="font-title text-4xl font-semibold text-crema">
          Configuración<span className="text-arcilla">.</span>
        </h1>
      </div>

      {/* Pestañas */}
      <div className="flex flex-wrap gap-1.5 border-b border-musgo/15 pb-3">
        {visibleTabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-2 px-4 h-9 rounded-full font-mono text-xs transition-colors",
              tab === t.id
                ? "bg-arcilla/15 border border-arcilla/30 text-arcilla/90"
                : "border border-transparent text-crema/40 hover:text-crema/70 hover:bg-musgo/10",
            )}>
            <t.icon size={13} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Contenido de cada pestaña */}
      {tab === "perfil" && (
        <div className="space-y-6">
          <Card title="Perfil">
            <Row icon={User}       label="Nombre"  value={user?.fullName ?? ""} />
            <Row icon={Mail}       label="Correo"  value={user?.email ?? ""} />
            <Row icon={BadgeCheck} label="Rol"     value={user ? (ROLE_LABEL[user.role] ?? user.role) : ""} />
            <Row icon={Building2}  label="Usuario" value={user?.username ?? ""} />
          </Card>

          <Card title="Sesión">
            <button
              onClick={logout}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-[0.65rem] text-red-400/80 hover:bg-red-900/15 hover:text-red-400 transition-colors text-sm font-sans"
            >
              <LogOut size={15} />
              Cerrar sesión
            </button>
          </Card>
        </div>
      )}
`r`n
      {tab === "servidores" && isAdmin && (
        <div className="space-y-3">
          <p className="font-mono text-[11px] text-crema/40 leading-relaxed">
            Da de alta los servidores Core y sus <span className="text-arcilla/80">rutas autorizadas</span>.
            Estos servidores aparecen luego en <span className="text-crema/70">Limpieza</span> para operar.
            La contraseña o llave .pem se introduce al conectar; nunca se guarda aquí.
          </p>
          <CleanupServersAdmin />
        </div>
      )}

      {tab === "apariencia" && (
        <Card title="Apariencia">
          <button
            onClick={toggle}
            className="w-full flex items-center justify-between py-2 group"
          >
            <div className="flex items-center gap-3">
              {theme === "dark" ? <Moon size={15} className="text-crema/50" /> : <Sun size={15} className="text-crema/50" />}
              <span className="font-sans text-sm text-crema/75">Tema {theme === "dark" ? "oscuro" : "claro"}</span>
            </div>
            <span className="font-mono text-[11px] text-arcilla/70 group-hover:text-arcilla transition-colors">
              Cambiar →
            </span>
          </button>
        </Card>
      )}
    </div>
  );
}


