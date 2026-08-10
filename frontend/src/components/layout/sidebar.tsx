"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Database,
  FolderSync,
  Monitor,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  User,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/useAuth";

function UserBadge({ collapsed }: { collapsed: boolean }) {
  const user = useAuthStore((s) => s.user);
  const { logout } = useAuth();
  const initials = user?.fullName
    ? user.fullName.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  return (
    <button
      onClick={logout}
      title="Cerrar sesión"
      className={cn(
        "w-full flex items-center gap-3 px-3 h-10 rounded-[0.75rem] cursor-pointer text-left",
        "text-crema/45 hover:bg-red-900/20 hover:text-crema/80 transition-all duration-150",
        collapsed && "justify-center px-0"
      )}
    >
      <div className="w-[18px] h-[18px] rounded-full bg-musgo/60 border border-musgo/40 flex items-center justify-center shrink-0">
        <span className="font-mono text-[8px] text-crema/70">{initials}</span>
      </div>
      {!collapsed && (
        <span className="text-sm font-sans truncate">{user?.fullName ?? "Mi cuenta"}</span>
      )}
    </button>
  );
}

const NAV_ITEMS = [
  { href: "/dashboard",        label: "Dashboard",       icon: LayoutDashboard },
  { href: "/dashboard/backups",   label: "Backups",         icon: Database        },
  { href: "/dashboard/cleanup",   label: "Archivos",        icon: FolderSync      },
  { href: "/dashboard/limpieza-remota", label: "Limpieza", icon: ShieldCheck },
  { href: "/dashboard/access",    label: "Acceso Remoto",   icon: Monitor         },
  { href: "/dashboard/alerts",    label: "Notificaciones",  icon: Bell            },
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
        "relative flex flex-col h-screen bg-carbon border-r border-musgo/20",
        "transition-all duration-300 ease-power3-out shrink-0",
        collapsed ? "w-[68px]" : "w-[220px]"
      )}
    >
      {/* Logo */}
      <div className={cn(
        "flex items-center h-16 px-4 border-b border-musgo/20",
        collapsed ? "justify-center" : "gap-3"
      )}>
        <span className="w-7 h-7 rounded-full bg-arcilla flex items-center justify-center shrink-0">
          <span className="w-3 h-3 rounded-full bg-crema/90" />
        </span>
        {!collapsed && (
          <span className="font-mono text-xs text-crema/50 tracking-wide truncate">
            infra platform
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 h-10 rounded-[0.75rem]",
                "text-sm font-sans transition-all duration-150",
                active
                  ? "bg-musgo/40 text-crema"
                  : "text-crema/45 hover:bg-musgo/20 hover:text-crema/80",
                collapsed && "justify-center px-0"
              )}
              title={collapsed ? label : undefined}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="py-4 px-2 space-y-1 border-t border-musgo/20">
        {BOTTOM_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 h-10 rounded-[0.75rem]",
              "text-sm font-sans text-crema/45 hover:bg-musgo/20 hover:text-crema/80 transition-all duration-150",
              collapsed && "justify-center px-0"
            )}
            title={collapsed ? label : undefined}
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </Link>
        ))}

        {/* Profile */}
        <UserBadge collapsed={collapsed} />
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        aria-label={collapsed ? "Expandir menú lateral" : "Colapsar menú lateral"}
        aria-expanded={!collapsed}
        className={cn(
          "absolute -right-3 top-[4.5rem] z-20",
          "w-6 h-6 rounded-full bg-carbon border border-musgo/40",
          "flex items-center justify-center text-crema/40 hover:text-crema hover:border-musgo/80",
          "transition-all duration-150"
        )}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  );
}
