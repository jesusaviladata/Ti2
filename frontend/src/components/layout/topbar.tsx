"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Bell, Sun, Moon, X,
  LogOut, User, Database, Monitor, ShieldAlert,
  AlertTriangle, CheckCircle2, Trash2,
} from "lucide-react";
import type { User as AuthUser } from "@/types";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/components/providers/theme-provider";
import { StorageHealthIndicator } from "@/components/layout/storage-health-indicator";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────
interface SearchItem {
  id: string;
  type: "backup" | "access";
  title: string;
  subtitle: string;
  href: string;
}

interface SearchResults {
  items: SearchItem[];
  total: number;
}

type SearchStatus = "idle" | "loading" | "success" | "error";

interface Notification {
  id: string;
  kind: "backup_fail" | "backup_success" | "suspicious" | "test";
  title: string;
  body: string;
  ts: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function timeAgo(iso: string) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  return `hace ${Math.floor(hrs / 24)}d`;
}

function statusDot(status: string) {
  switch (status) {
    case "completed": return "text-green-400";
    case "failed":    return "text-red-400";
    case "active":    return "text-blue-400";
    default:          return "text-crema/35";
  }
}

// ── Search panel ──────────────────────────────────────────────────────────────
function SearchPanel({
  query, results, status, onClose, onSelect,
}: {
  query: string;
  results: SearchResults | null;
  status: SearchStatus;
  onClose: () => void;
  onSelect: (href: string) => void;
}) {
  const items = results?.items ?? [];
  const backups = items.filter((item) => item.type === "backup");
  const access = items.filter((item) => item.type === "access");
  const hasBackups = backups.length > 0;
  const hasAccess = access.length > 0;
  const hasAny = hasBackups || hasAccess;

  return (
    <div
      id="global-search-results"
      className="absolute left-0 top-full mt-2 w-full min-w-[420px] z-[60] rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden"
    >
      {/* Loading / empty */}
      {status === "loading" && (
        <div className="px-4 py-5 text-center">
          <p role="status" className="font-mono text-xs text-crema/40">Buscando…</p>
        </div>
      )}
      {status === "error" && (
        <div className="px-4 py-5 text-center">
          <p role="alert" className="font-mono text-xs text-red-300/80">
            No se pudo realizar la búsqueda. Inténtalo nuevamente.
          </p>
        </div>
      )}
      {status === "success" && !hasAny && (
        <div className="px-4 py-5 text-center">
          <p className="font-mono text-xs text-crema/25">Sin resultados para &ldquo;{query}&rdquo;</p>
        </div>
      )}

      {/* Backups section */}
      {hasBackups && (
        <div>
          <div className="flex items-center gap-2 px-4 pt-3 pb-1.5">
            <Database size={10} className="text-crema/30" />
            <span className="font-mono text-[9px] text-crema/30 uppercase tracking-widest">Backups</span>
          </div>
          {backups.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelect(item.href)}
              className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-musgo/10 transition-colors focus-visible:outline-none focus-visible:bg-musgo/15"
            >
              <p className="flex-1 min-w-0 font-sans text-sm text-crema/80 truncate">{item.title}</p>
              <span className={cn("font-mono text-[10px] shrink-0", statusDot(item.subtitle))}>
                {item.subtitle}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Access section */}
      {hasAccess && (
        <div className={hasBackups ? "border-t border-musgo/15" : ""}>
          <div className="flex items-center gap-2 px-4 pt-3 pb-1.5">
            <Monitor size={10} className="text-crema/30" />
            <span className="font-mono text-[9px] text-crema/30 uppercase tracking-widest">Acceso Remoto</span>
          </div>
          {access.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelect(item.href)}
              className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-musgo/10 transition-colors focus-visible:outline-none focus-visible:bg-musgo/15"
            >
              <div className="flex-1 min-w-0">
                <p className="font-sans text-sm text-crema/80 truncate">{item.title}</p>
                {item.subtitle && (
                  <p className="font-mono text-[10px] text-crema/35 truncate">{item.subtitle}</p>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-musgo/15 px-4 py-2 flex items-center justify-between">
        <span className="font-mono text-[9px] text-crema/20">Esc para cerrar</span>
        <button
          onClick={onClose}
          className="text-crema/25 hover:text-crema/60 transition-colors"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

// ── Notifications panel ───────────────────────────────────────────────────────
function NotificationsPanel({
  notifications, onClose, onClear, clearing,
}: {
  notifications: Notification[];
  onClose: () => void;
  onClear: () => void;
  clearing: boolean;
}) {
  return (
    <div className="absolute right-0 top-full mt-2 w-[300px] z-[60] rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-musgo/15">
        <span className="font-sans text-sm font-medium text-crema/70">Notificaciones</span>
        <div className="flex items-center gap-2">
          {notifications.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              disabled={clearing}
              className="flex items-center gap-1 font-mono text-[9px] text-crema/30 transition-colors hover:text-red-300 disabled:opacity-40"
            >
              <Trash2 size={11} /> {clearing ? "Limpiando…" : "Limpiar"}
            </button>
          )}
          <button onClick={onClose} className="text-crema/25 hover:text-crema/60 transition-colors">
            <X size={13} />
          </button>
        </div>
      </div>

      {notifications.length === 0 ? (
        <div className="px-4 py-8 text-center space-y-2">
          <CheckCircle2 size={20} className="text-crema/15 mx-auto" />
          <p className="font-mono text-xs text-crema/25">Sin notificaciones</p>
        </div>
      ) : (
        <div className="max-h-[320px] overflow-y-auto">
          {notifications.map((n) => (
            <div
              key={n.id}
              className="flex items-start gap-3 px-4 py-3 hover:bg-musgo/10 transition-colors border-b border-musgo/10 last:border-0"
            >
              <div className="mt-0.5 shrink-0">
                {n.kind === "backup_fail" && <AlertTriangle size={13} className="text-red-400/80" />}
                {n.kind === "backup_success" && <CheckCircle2 size={13} className="text-green-400/80" />}
                {n.kind !== "backup_fail" && n.kind !== "backup_success" && <ShieldAlert size={13} className="text-orange-400/80" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-sans text-xs font-medium text-crema/80">{n.title}</p>
                <p className="font-mono text-[10px] text-crema/40 mt-0.5 truncate">{n.body}</p>
              </div>
              <span className="font-mono text-[9px] text-crema/25 shrink-0 mt-0.5">
                {timeAgo(n.ts)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Profile dropdown ──────────────────────────────────────────────────────────
function ProfileDropdown({
  user, onLogout, onClose,
}: {
  user: AuthUser | null;
  onLogout: () => void;
  onClose: () => void;
}) {
  const initials = user?.fullName
    ? user.fullName.split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase()
    : "??";

  return (
    <div className="absolute right-0 top-full mt-2 w-[210px] z-[60] rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
      <div className="px-4 py-4 border-b border-musgo/15">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-musgo border border-musgo/60 flex items-center justify-center shrink-0">
            <span className="font-mono text-sm text-crema/70">{initials}</span>
          </div>
          <div className="min-w-0">
            <p className="font-sans text-sm font-medium text-crema/90 truncate">
              {user?.fullName ?? "Usuario"}
            </p>
            <p className="font-mono text-[10px] text-crema/40 truncate">
              {user?.email ?? ""}
            </p>
          </div>
        </div>
      </div>

      <div className="p-2">
        <button className="w-full flex items-center gap-3 px-3 py-2 rounded-[0.5rem] text-crema/55 hover:bg-musgo/15 hover:text-crema/90 transition-colors text-sm font-sans">
          <User size={14} />
          Mi perfil
        </button>
        <button
          onClick={() => { onClose(); onLogout(); }}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-[0.5rem] text-red-400/70 hover:bg-red-900/15 hover:text-red-400 transition-colors text-sm font-sans mt-0.5"
        >
          <LogOut size={14} />
          Cerrar sesión
        </button>
      </div>
    </div>
  );
}

// ── Main Topbar ───────────────────────────────────────────────────────────────
export function Topbar() {
  const router = useRouter();
  const { theme, toggle: toggleTheme } = useTheme();
  const user = useAuthStore((s) => s.user);
  const { logout } = useAuth();

  // Search
  const [query,       setQuery]       = useState("");
  const [results,      setResults]      = useState<SearchResults | null>(null);
  const [searchStatus, setSearchStatus] = useState<SearchStatus>("idle");
  const [searchOpen,   setSearchOpen]   = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Notifications
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [readIds,        setReadIds]       = useState<Set<string>>(new Set());
  const [notifOpen,      setNotifOpen]     = useState(false);
  const [clearingNotifs, setClearingNotifs] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  // Profile / settings
  const [profileOpen,  setProfileOpen]  = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  // ── Keyboard shortcut Ctrl+K / ⌘K ──────────────────────────────────────────
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
        searchRef.current?.querySelector("input")?.focus();
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setNotifOpen(false);
        setProfileOpen(false);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── Click-outside detection ─────────────────────────────────────────────────
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (searchOpen  && searchRef.current  && !searchRef.current.contains(e.target as Node))  setSearchOpen(false);
      if (notifOpen   && notifRef.current   && !notifRef.current.contains(e.target as Node))    setNotifOpen(false);
      if (profileOpen && profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [searchOpen, notifOpen, profileOpen]);

  // ── Debounced search ────────────────────────────────────────────────────────
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      setSearchStatus("idle");
      return;
    }

    let cancelled = false;
    setResults(null);
    setSearchStatus("loading");

    const timeoutId = setTimeout(async () => {
      try {
        const response = await api.get<SearchResults>(
          `/api/v1/search?q=${encodeURIComponent(query.trim())}`,
        );
        if (cancelled) return;

        const items = Array.isArray(response.data?.items) ? response.data.items : [];
        setResults({
          items,
          total: typeof response.data?.total === "number" ? response.data.total : items.length,
        });
        setSearchStatus("success");
      } catch {
        if (cancelled) return;
        setResults(null);
        setSearchStatus("error");
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [query]);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    setQuery("");
    setResults(null);
    setSearchStatus("idle");
  }, []);

  const selectSearchResult = useCallback((href: string) => {
    closeSearch();
    router.push(href);
  }, [closeSearch, router]);

  // ── Poll notifications every 30 s ──────────────────────────────────────────
  const loadNotifs = useCallback(async () => {
    try {
      const r = await api.get("/api/v1/notifications");
      setNotifications(r.data.notifications ?? []);
    } catch {}
  }, []);

  useEffect(() => {
    loadNotifs();
    const id = setInterval(loadNotifs, 30_000);
    return () => clearInterval(id);
  }, [loadNotifs]);

  useEffect(() => {
    const cleared = () => {
      setNotifications([]);
      setReadIds(new Set());
    };
    window.addEventListener("data-express:notifications-cleared", cleared);
    return () => window.removeEventListener("data-express:notifications-cleared", cleared);
  }, []);

  const clearNotifs = useCallback(async () => {
    setClearingNotifs(true);
    try {
      await api.delete("/api/v1/notifications");
      setNotifications([]);
      setReadIds(new Set());
      window.dispatchEvent(new Event("data-express:notifications-cleared"));
    } finally {
      setClearingNotifs(false);
    }
  }, []);

  const unread = notifications.filter((n) => !readIds.has(n.id)).length;

  const initials = user?.fullName
    ? user.fullName.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()
    : "??";

  return (
    <header className="relative z-40 flex h-16 shrink-0 items-center gap-3 border-b border-musgo/20 px-6">
      {/* ── Search ─────────────────────────────────────────────────────────── */}
      <div ref={searchRef} className="relative flex min-w-0 w-full max-w-sm items-center">
        <Search size={14} className="absolute left-3 text-crema/30 z-10 pointer-events-none" />
        <input
          type="text"
          placeholder="Buscar..."
          aria-label="Buscar backups y sesiones de acceso"
          aria-controls="global-search-results"
          aria-expanded={searchOpen && query.trim().length >= 2}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSearchOpen(true); }}
          onFocus={() => setSearchOpen(true)}
          className="w-full h-9 bg-musgo/10 border border-musgo/20 rounded-pill pl-9 pr-10 text-sm text-crema placeholder:text-crema/25 focus:outline-none focus:border-musgo/50 transition-colors"
        />
        {query ? (
          <button
            onClick={closeSearch}
            aria-label="Limpiar búsqueda"
            className="absolute right-3 text-crema/30 hover:text-crema/60 transition-colors"
          >
            <X size={13} />
          </button>
        ) : (
          <kbd className="absolute right-3 font-mono text-[10px] text-crema/20 border border-musgo/20 rounded px-1 pointer-events-none">
            ⌘K
          </kbd>
        )}

        {searchOpen && query.trim().length >= 2 && (
          <SearchPanel
            query={query}
            results={results}
            status={searchStatus}
            onClose={closeSearch}
            onSelect={selectSearchResult}
          />
        )}
      </div>

      {/* ── Agent storage ─────────────────────────────────────────────────── */}
      <StorageHealthIndicator />

      {/* ── Right actions ──────────────────────────────────────────────────── */}
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          aria-label={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          className="w-9 h-9 rounded-[0.75rem] flex items-center justify-center text-crema/40 hover:bg-musgo/20 hover:text-crema/80 transition-all"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Notifications */}
        <div ref={notifRef} className="relative">
          <button
            onClick={() => {
              const next = !notifOpen;
              setNotifOpen(next);
              if (next) setReadIds(new Set(notifications.map((n) => n.id)));
            }}
            aria-label={`Notificaciones${unread > 0 ? ` (${unread} sin leer)` : ""}`}
            aria-haspopup="menu"
            aria-expanded={notifOpen}
            className="relative w-9 h-9 rounded-[0.75rem] flex items-center justify-center text-crema/40 hover:bg-musgo/20 hover:text-crema/80 transition-all"
          >
            <Bell size={16} />
            {unread > 0 && (
              <span className="absolute top-1.5 right-1.5 min-w-[14px] h-[14px] bg-arcilla rounded-full flex items-center justify-center px-0.5">
                <span className="font-mono text-[8px] text-crema leading-none">
                  {unread > 9 ? "9+" : unread}
                </span>
              </span>
            )}
          </button>
          {notifOpen && (
            <NotificationsPanel
              notifications={notifications}
              onClose={() => setNotifOpen(false)}
              onClear={clearNotifs}
              clearing={clearingNotifs}
            />
          )}
        </div>

        {/* Profile avatar */}
        <div ref={profileRef} className="relative ml-0.5">
          <button
            onClick={() => setProfileOpen((v) => !v)}
            aria-label="Menú de perfil"
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            className="w-8 h-8 rounded-full bg-musgo border border-musgo/60 flex items-center justify-center cursor-pointer hover:border-arcilla/50 transition-colors"
          >
            <span className="font-mono text-xs text-crema/60">{initials}</span>
          </button>
          {profileOpen && (
            <ProfileDropdown
              user={user}
              onLogout={logout}
              onClose={() => setProfileOpen(false)}
            />
          )}
        </div>
      </div>
    </header>
  );
}
