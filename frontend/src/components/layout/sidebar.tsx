"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  ChevronLeft,
  ChevronRight,
  Database,
  FolderSync,
  LayoutDashboard,
  Monitor,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/useAuth";
import { BackupBackgroundIndicator } from "@/components/backups/backup-background-indicator";

function UserBadge({ collapsed }: { collapsed: boolean }) {
  const user = useAuthStore((state) => state.user);
  const { logout } = useAuth();
  const initials = user?.fullName
    ? user.fullName.split(" ").map((name) => name[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  return (
    <button
      type="button"
      onClick={logout}
      title="Cerrar sesión"
      className={cn(
        "flex h-10 w-full cursor-pointer items-center gap-3 rounded-[0.75rem] px-3 text-left text-crema/45 transition-all duration-150 hover:bg-red-900/20 hover:text-crema/80",
        collapsed && "justify-center px-0",
      )}
    >
      <div className="flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full border border-arcilla/35 bg-arcilla/15">
        <span className="font-mono text-[8px] text-crema/75">{initials}</span>
      </div>
      {!collapsed ? <span className="truncate text-sm">{user?.fullName ?? "Mi cuenta"}</span> : null}
    </button>
  );
}

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard/backups", label: "Backups", icon: Database },
  { href: "/dashboard/cleanup", label: "Archivos", icon: FolderSync },
  { href: "/dashboard/limpieza-remota", label: "Limpieza", icon: ShieldCheck },
  { href: "/dashboard/access", label: "Acceso Remoto", icon: Monitor },
  { href: "/dashboard/alerts", label: "Notificaciones", icon: Bell },
];

const BOTTOM_ITEMS = [
  { href: "/dashboard/settings", label: "Configuración", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "relative flex h-screen shrink-0 flex-col border-r border-musgo/30 bg-carbon transition-all duration-300 ease-power3-out",
        collapsed ? "w-[72px]" : "w-[240px]",
      )}
    >
      <div className={cn("flex h-[72px] items-center border-b border-musgo/25 px-3", collapsed ? "justify-center" : "gap-3")}>
        <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[0.7rem] bg-white p-0.5">
          <Image
            src="/brand/data-express-logo.png"
            alt=""
            width={44}
            height={44}
            className="h-full w-full object-contain"
          />
        </div>
        {!collapsed ? (
          <span className="min-w-0 leading-tight text-crema">
            <span className="block truncate text-sm font-semibold">Data Express</span>
            <span className="block truncate text-[10px] uppercase tracking-[0.14em] text-arcilla">Latinoamérica</span>
          </span>
        ) : null}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4" aria-label="Navegación principal">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex h-10 items-center gap-3 rounded-[0.75rem] px-3 text-sm transition-all duration-150",
                active
                  ? "bg-arcilla/15 text-crema"
                  : "text-crema/45 hover:bg-musgo/25 hover:text-crema/80",
                collapsed && "justify-center px-0",
              )}
              title={collapsed ? label : undefined}
            >
              <Icon size={18} className={cn("shrink-0", active && "text-arcilla")} />
              {!collapsed ? <span className="truncate">{label}</span> : null}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-musgo/25 px-2 py-4">
        <BackupBackgroundIndicator collapsed={collapsed} />
        {BOTTOM_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex h-10 items-center gap-3 rounded-[0.75rem] px-3 text-sm transition-all duration-150",
                active ? "bg-arcilla/15 text-crema" : "text-crema/45 hover:bg-musgo/25 hover:text-crema/80",
                collapsed && "justify-center px-0",
              )}
              title={collapsed ? label : undefined}
            >
              <Icon size={18} className={cn("shrink-0", active && "text-arcilla")} />
              {!collapsed ? <span className="truncate">{label}</span> : null}
            </Link>
          );
        })}
        <UserBadge collapsed={collapsed} />
      </div>

      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-label={collapsed ? "Expandir menú lateral" : "Colapsar menú lateral"}
        aria-expanded={!collapsed}
        className="absolute -right-3 top-[5.25rem] z-20 flex h-6 w-6 items-center justify-center rounded-full border border-musgo/50 bg-carbon text-crema/40 transition-all duration-150 hover:border-arcilla/60 hover:text-crema"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  );
}
