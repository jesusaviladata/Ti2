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
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { useNavStore } from "@/store/nav.store";
import { BackupBackgroundIndicator } from "@/components/backups/backup-background-indicator";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard/backups", label: "Backups", icon: Database },
  { href: "/dashboard/file-backups", label: "Copias de archivos", icon: FolderSync },
  { href: "/dashboard/cleanup", label: "Limpieza", icon: ShieldCheck },
  { href: "/dashboard/access", label: "Acceso remoto", icon: Monitor },
  { href: "/dashboard/alerts", label: "Notificaciones", icon: Bell },
];

const BOTTOM_ITEMS = [
  { href: "/dashboard/settings", label: "Configuración", icon: Settings },
];

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  collapsed,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  active: boolean;
  collapsed: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      title={collapsed ? label : undefined}
      className={cn(
        "relative flex h-9 items-center gap-3 rounded-[0.6rem] px-3 text-sm transition-colors duration-150",
        active
          ? "bg-crema/[0.07] font-medium text-crema"
          : "text-crema/60 hover:bg-crema/[0.04] hover:text-crema",
        collapsed && "justify-center px-0",
      )}
    >
      {active ? (
        <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-arcilla" />
      ) : null}
      <Icon size={17} strokeWidth={1.75} className={cn("shrink-0", active ? "text-arcilla" : "text-crema/50")} />
      {!collapsed ? <span className="truncate">{label}</span> : null}
    </Link>
  );
}

/** Acceso a la cuenta: lleva a Configuración. Cerrar sesión vive en el menú de perfil de la barra superior. */
function AccountLink({ collapsed }: { collapsed: boolean }) {
  const user = useAuthStore((state) => state.user);
  const initials = user?.fullName
    ? user.fullName.split(" ").map((name) => name[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  return (
    <Link
      href="/dashboard/settings"
      title={collapsed ? user?.fullName ?? "Mi cuenta" : undefined}
      className={cn(
        "flex h-11 items-center gap-3 rounded-[0.6rem] px-3 text-left transition-colors duration-150 hover:bg-crema/[0.04]",
        collapsed && "justify-center px-0",
      )}
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-arcilla/15 text-[11px] font-semibold text-arcilla">
        {initials}
      </span>
      {!collapsed ? (
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-sm text-crema/85">{user?.fullName ?? "Mi cuenta"}</span>
          {user?.email ? <span className="block truncate text-xs text-crema/50">{user.email}</span> : null}
        </span>
      ) : null}
    </Link>
  );
}

function SidebarContent({
  collapsed,
  pathname,
  onClose,
}: {
  collapsed: boolean;
  pathname: string;
  onClose?: () => void;
}) {
  return (
    <>
      <div className={cn("flex h-16 shrink-0 items-center px-3", collapsed ? "justify-center" : "gap-3")}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-[0.55rem] bg-white p-0.5">
          <Image src="/brand/data-express-logo.png" alt="" width={36} height={36} className="h-full w-full object-contain" />
        </div>
        {!collapsed ? (
          <span className="min-w-0 flex-1 leading-tight text-crema">
            <span className="block truncate text-sm font-semibold">Data Express</span>
            <span className="block truncate text-xs text-crema/50">Latinoamérica</span>
          </span>
        ) : null}
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar menú"
            className="flex h-9 w-9 items-center justify-center rounded-[0.6rem] text-crema/60 hover:bg-crema/[0.05] hover:text-crema"
          >
            <X size={18} />
          </button>
        ) : null}
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3" aria-label="Navegación principal">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} active={pathname === item.href} collapsed={collapsed} />
        ))}
      </nav>

      <div className="space-y-0.5 border-t border-crema/[0.06] px-2 py-3">
        <BackupBackgroundIndicator collapsed={collapsed} />
        {BOTTOM_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} active={pathname === item.href} collapsed={collapsed} />
        ))}
        <AccountLink collapsed={collapsed} />
      </div>
    </>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const mobileOpen = useNavStore((state) => state.mobileOpen);
  const setMobileOpen = useNavStore((state) => state.setMobileOpen);

  // Cierra el panel móvil al navegar.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname, setMobileOpen]);

  // Bloquea el scroll del fondo y permite cerrar con Escape mientras el panel está abierto.
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen, setMobileOpen]);

  return (
    <>
      {/* Escritorio: columna fija y plegable */}
      <aside
        className={cn(
          "relative hidden h-screen shrink-0 flex-col border-r border-crema/[0.06] bg-carbon transition-[width] duration-200 ease-out-strong lg:flex",
          collapsed ? "w-[68px]" : "w-[232px]",
        )}
      >
        <SidebarContent collapsed={collapsed} pathname={pathname} />
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expandir menú lateral" : "Colapsar menú lateral"}
          aria-expanded={!collapsed}
          className="absolute -right-3 top-[4.75rem] z-20 flex h-6 w-6 items-center justify-center rounded-full border border-crema/10 bg-carbon text-crema/50 transition-colors duration-150 hover:border-arcilla/60 hover:text-crema"
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      </aside>

      {/* Móvil y tablet: panel deslizante */}
      <div className={cn("fixed inset-0 z-50 lg:hidden", mobileOpen ? "pointer-events-auto" : "pointer-events-none")}>
        <div
          aria-hidden="true"
          onClick={() => setMobileOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/55 transition-opacity duration-200 ease-out-strong",
            mobileOpen ? "opacity-100" : "opacity-0",
          )}
        />
        <aside
          id="menu-movil"
          role="dialog"
          aria-modal="true"
          aria-label="Menú de navegación"
          aria-hidden={!mobileOpen}
          inert={!mobileOpen}
          className={cn(
            "absolute inset-y-0 left-0 flex w-[min(280px,85vw)] flex-col border-r border-crema/[0.06] bg-carbon shadow-[8px_0_32px_rgba(0,0,0,0.35)] transition-transform duration-[240ms] ease-out-strong",
            mobileOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <SidebarContent collapsed={false} pathname={pathname} onClose={() => setMobileOpen(false)} />
        </aside>
      </div>
    </>
  );
}
