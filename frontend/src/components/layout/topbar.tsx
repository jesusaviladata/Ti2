"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Search, Bell, Settings, Sun, Moon, X,
  LogOut, User, Database, Monitor, ShieldAlert,
  AlertTriangle, CheckCircle2,
} from "lucide-react";
import type { User as AuthUser } from "@/types";
import { useAuthStore } from "@/store/auth.store";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/components/providers/theme-provider";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────
interface SearchItem {
  id: string;
  label: string;
  sub: string;
  status: string;
}

interface SearchResults {
  backups: SearchItem[];
  access: SearchItem[];
}

interface Notification {
  id: string;
  kind: "backup_fail" | "suspicious";
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
  query, results, onClose,
}: {
  query: string;
  results: SearchResults | null;
  onClose: () => void;
}) {
  const hasBackups = (results?.backups.length ?? 0) > 0;
  const hasAccess  = (results?.access.length  ?? 0) > 0;
  const hasAny     = hasBackups || hasAccess;

  return (
    <div className="absolute left-0 top-full mt-2 w-full min-w-[420px] z-[60] rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
      {/* Loading / empty */}
      {!results && (
        <div className="px-4 py-5 text-center">
          <p className="font-mono text-xs text-crema/25">Buscando…</p>
        </div>
      )}
      {results && !hasAny && (
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
          {results!.backups.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-4 py-2 hover:bg-musgo/10 cursor-pointer transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="font-sans text-sm text-crema/80 truncate">{item.label}</p>
                {item.sub && (
                  <p className="font-mono text-[10px] text-crema/35 truncate">{item.sub}</p>
                )}
              </div>
              <span className={cn("font-mono text-[10px] shrink-0", statusDot(item.status))}>
                {item.status}
              </span>
            </div>
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
          {results!.access.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-4 py-2 hover:bg-musgo/10 cursor-pointer transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="font-sans text-sm text-crema/80 truncate">{item.label}</p>
                {item.sub && (
                  <p className="font-mono text-[10px] text-crema/35 truncate">{item.sub}</p>
                )}
              </div>
              <span className={cn("font-mono text-[10px] shrink-0", statusDot(item.status))}>
                {item.status}
              </span>
            </div>
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
  notifications, onClose,
}: {
  notifications: Notification[];
  onClose: () => void;
}) {
  return (
    <div className="absolute right-0 top-full mt-2 w-[300px] z-[60] rounded-[1rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-musgo/15">
        <span className="font-sans text-sm font-medium text-crema/70">Notificaciones</span>
        <button onClick={onClose} className="text-crema/25 hover:text-crema/60 transition-colors">
          <X size={13} />
        </button>
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
                {n.kind === "backup_fail"
                  ? <AlertTriangle size={13} className="text-red-400/80" />
                  : <ShieldAlert   size={13} className="text-orange-400/80" />
                }
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

// ── Settings modal ────────────────────────────────────────────────────────────
function SettingsModal({ onClose }: { onClose: () => void }) {
  const { theme, toggle } = useTheme();

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="absolute inset-0 bg-carbon/70 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-modal-title"
        className="relative z-10 w-full max-w-md mx-4 rounded-[1.5rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-musgo/20">
          <h2 id="settings-modal-title" className="font-display text-2xl italic font-light text-crema">
            Configuración<span className="text-arcilla">.</span>
          </h2>
          <button onClick={onClose} aria-label="Cerrar" className="text-crema/30 hover:text-crema/70 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Appearance */}
          <section>
            <p className="font-mono text-[10px] text-arcilla uppercase tracking-[0.15em] mb-3">
              Apariencia
            </p>
            <div className="flex items-center justify-between rounded-[0.75rem] bg-musgo/10 border border-musgo/20 px-4 py-3">
              <div>
                <p className="font-sans text-sm text-crema/80">Tema</p>
                <p className="font-mono text-[10px] text-crema/35 mt-0.5">
                  {theme === "dark" ? "Modo oscuro activo" : "Modo claro activo"}
                </p>
              </div>
              {/* Toggle switch */}
              <button
                onClick={toggle}
                className={cn(
                  "relative w-11 h-6 rounded-full transition-colors duration-200 flex-shrink-0",
                  theme === "light" ? "bg-arcilla" : "bg-musgo/60"
                )}
              >
                <span
                  className={cn(
                    "absolute top-1 w-4 h-4 rounded-full bg-crema shadow transition-all duration-200",
                    theme === "light" ? "left-6" : "left-1"
                  )}
                />
              </button>
            </div>
          </section>

          {/* System info */}
          <section>
            <p className="font-mono text-[10px] text-arcilla uppercase tracking-[0.15em] mb-3">
              Sistema
            </p>
            <div className="rounded-[0.75rem] bg-musgo/10 border border-musgo/20 px-4 py-3 space-y-2">
              <div className="flex justify-between">
                <span className="font-mono text-[11px] text-crema/40">Versión</span>
                <span className="font-mono text-[11px] text-crema/60">0.5.0</span>
              </div>
              <div className="flex justify-between">
                <span className="font-mono text-[11px] text-crema/40">Entorno</span>
                <span className="font-mono text-[11px] text-crema/60">desarrollo</span>
              </div>
              <div className="flex justify-between">
                <span className="font-mono text-[11px] text-crema/40">API</span>
                <span className="font-mono text-[11px] text-crema/60">mismo origen</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

// ── Main Topbar ───────────────────────────────────────────────────────────────
export function Topbar() {
  const { theme, toggle: toggleTheme } = useTheme();
  const user = useAuthStore((s) => s.user);
  const { logout } = useAuth();

  // Search
  const [query,       setQuery]       = useState("");
  const [results,     setResults]     = useState<SearchResults | null>(null);
  const [searchOpen,  setSearchOpen]  = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Notifications
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [readIds,        setReadIds]       = useState<Set<string>>(new Set());
  const [notifOpen,      setNotifOpen]     = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  // Profile / settings
  const [profileOpen,  setProfileOpen]  = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
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
        setSettingsOpen(false);
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
    if (query.length < 2) { setResults(null); return; }
    const t = setTimeout(async () => {
      try {
        const r = await api.get(`/api/v1/search?q=${encodeURIComponent(query)}`);
        setResults(r.data);
      } catch { setResults(null); }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

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

  const unread = notifications.filter((n) => !readIds.has(n.id)).length;

  const initials = user?.fullName
    ? user.fullName.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()
    : "??";

  return (
    <header className="flex items-center justify-between h-16 px-6 border-b border-musgo/20 shrink-0">
      {/* ── Search ─────────────────────────────────────────────────────────── */}
      <div ref={searchRef} className="relative flex items-center w-full max-w-sm">
        <Search size={14} className="absolute left-3 text-crema/30 z-10 pointer-events-none" />
        <input
          type="text"
          placeholder="Buscar..."
          aria-label="Buscar backups y sesiones de acceso"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSearchOpen(true); }}
          onFocus={() => setSearchOpen(true)}
          className="w-full h-9 bg-musgo/10 border border-musgo/20 rounded-pill pl-9 pr-10 text-sm text-crema placeholder:text-crema/25 focus:outline-none focus:border-musgo/50 transition-colors"
        />
        {query ? (
          <button
            onClick={() => { setQuery(""); setResults(null); setSearchOpen(false); }}
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

        {searchOpen && query.length >= 2 && (
          <SearchPanel
            query={query}
            results={results}
            onClose={() => { setSearchOpen(false); setQuery(""); setResults(null); }}
          />
        )}
      </div>

      {/* ── Right actions ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 ml-4 shrink-0">
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
            />
          )}
        </div>

        {/* Settings */}
        <button
          onClick={() => setSettingsOpen(true)}
          aria-label="Configuración"
          className="w-9 h-9 rounded-[0.75rem] flex items-center justify-center text-crema/40 hover:bg-musgo/20 hover:text-crema/80 transition-all"
        >
          <Settings size={16} />
        </button>

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

      {/* Settings modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </header>
  );
}
