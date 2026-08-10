"use client";

import { useState } from "react";
import { Eye, EyeOff, Mail, Lock, AlertCircle, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

// ── Input field ───────────────────────────────────────────────────────────────
const INPUT_CLS = "w-full h-11 rounded-[0.75rem] bg-white/[0.06] border border-white/[0.08] px-3.5 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-white/25 transition-colors";

// ── Page ──────────────────────────────────────────────────────────────────────
// Solo inicio de sesión. El alta de cuentas es una operación de administración
// (endpoint protegido por rol admin), no un registro público desde el login.
export default function LoginPage() {
  const router = useRouter();
  const { login, loading, error } = useAuth();

  const [email,     setEmail]     = useState("");
  const [password,  setPassword]  = useState("");
  const [showPass,  setShowPass]  = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    try {
      await login(email, password);
    } catch {}
  }


  return (
    <div className="min-h-screen bg-[#080808] flex items-center justify-center relative overflow-hidden px-4">
      {/* ── Bokeh background ────────────────────────────────────────────────── */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute bottom-[-120px] left-[-80px]  w-[480px] h-[480px] rounded-full bg-red-600/30   blur-[130px]" />
        <div className="absolute bottom-[-80px]  right-[-60px] w-[380px] h-[380px] rounded-full bg-purple-700/25 blur-[110px]" />
        <div className="absolute top-[-60px]     right-[180px] w-[260px] h-[260px] rounded-full bg-blue-600/15  blur-[90px]"  />
      </div>

      {/* ── Card ────────────────────────────────────────────────────────────── */}
      <div className="relative w-full max-w-[400px] rounded-[1.75rem] bg-[#111111]/95 border border-white/[0.07] shadow-2xl">
        {/* Close button */}
        <button
          onClick={() => router.push("/")}
          className="absolute top-4 right-4 w-8 h-8 rounded-full bg-white/[0.08] flex items-center justify-center text-white/50 hover:bg-white/[0.14] hover:text-white transition-all z-10"
          aria-label="Cerrar"
        >
          <X size={14} />
        </button>

        <div className="px-7 pt-8 pb-8">
          {/* ── Sign In ───────────────────────────────────────────────────── */}
          <>
              <h1 className="text-white text-[1.4rem] font-semibold mb-1">
                Iniciar sesión
              </h1>
              <p className="text-white/35 text-xs mb-5">
                Acceso exclusivo para personal autorizado de Data Express.
              </p>

              <form onSubmit={handleLogin} className="space-y-3">
                <div className="relative">
                  <Mail size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none" />
                  <input
                    type="email"
                    placeholder="Correo electrónico"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    className={cn(INPUT_CLS, "pl-9")}
                  />
                </div>

                <div className="relative">
                  <Lock size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none" />
                  <input
                    type={showPass ? "text" : "password"}
                    placeholder="Contraseña"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    className={cn(INPUT_CLS, "pl-9 pr-10")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass((v) => !v)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
                    aria-label={showPass ? "Ocultar contraseña" : "Mostrar contraseña"}
                  >
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>

                {error && <ErrorBanner msg={error} />}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full h-11 mt-1 rounded-[0.75rem] bg-white text-[#111] font-semibold text-sm hover:bg-white/90 active:scale-[0.98] transition-all disabled:opacity-50"
                >
                  {loading ? "Ingresando…" : "Iniciar sesión"}
                </button>
              </form>
          </>

        </div>
      </div>
    </div>
  );
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div className="flex items-center gap-2 text-red-400 bg-red-400/[0.08] border border-red-400/[0.12] rounded-[0.65rem] px-3.5 py-2.5">
      <AlertCircle size={13} className="shrink-0" />
      <span className="text-xs">{msg}</span>
    </div>
  );
}
