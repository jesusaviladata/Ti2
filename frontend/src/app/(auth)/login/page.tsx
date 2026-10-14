"use client";

import Image from "next/image";
import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Lock, Mail, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const INPUT_CLASS =
  "h-12 w-full rounded-[0.8rem] border border-musgo/20 bg-inset/50 px-11 pr-4 text-sm text-crema outline-none transition-colors placeholder:text-subtle focus:border-arcilla/70 focus:ring-2 focus:ring-arcilla/15";

interface FieldErrors {
  email?: string;
  password?: string;
}

export default function LoginPage() {
  const router = useRouter();
  const { login, loading, error, clearError } = useAuth();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  function validate() {
    const nextErrors: FieldErrors = {};
    if (!email.trim()) nextErrors.email = "Ingresa tu correo electrónico.";
    else if (!EMAIL_PATTERN.test(email.trim())) nextErrors.email = "Ingresa un correo electrónico válido.";
    if (!password) nextErrors.password = "Ingresa tu contraseña.";

    setFieldErrors(nextErrors);
    if (nextErrors.email) emailRef.current?.focus();
    else if (nextErrors.password) passwordRef.current?.focus();
    return Object.keys(nextErrors).length === 0;
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    clearError();
    if (!validate()) return;
    try {
      await login(email, password);
    } catch {
      // El hook transforma el error técnico en un mensaje seguro para esta pantalla.
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-carbon px-4 py-8">
      <section className="relative grid w-full max-w-[880px] overflow-hidden rounded-[1.5rem] border border-musgo/20 bg-surface  md:grid-cols-[0.9fr_1.1fr]">
        <div className="relative flex min-h-[220px] flex-col items-center justify-center overflow-hidden bg-inset px-8 py-10 md:min-h-[560px]">
          <Image
            src="/brand/data-express-logo.png"
            alt="Data Express Latinoamérica"
            width={220}
            height={220}
            priority
            className="relative h-auto w-[170px] md:w-[220px]"
          />
          <p className="relative mt-5 max-w-[260px] text-center text-xs leading-relaxed text-muted">
            Operación segura de infraestructura, respaldos y acceso remoto.
          </p>
        </div>

        <div className="relative flex items-center px-6 py-10 sm:px-10 md:px-12">
          <button
            type="button"
            onClick={() => router.push("/")}
            aria-label="Cerrar"
            className="absolute right-5 top-5 flex h-9 w-9 items-center justify-center rounded-full text-subtle transition-colors hover:bg-inset hover:text-crema"
          >
            <X size={15} />
          </button>

          <div className="w-full">
            <p className="mb-2 font-sans text-xs uppercase tracking-[0.2em] text-arcilla">
              Acceso corporativo
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-crema">Iniciar sesión</h1>
            <p className="mb-7 mt-2 text-sm leading-relaxed text-muted">
              Ingresa con las credenciales proporcionadas por tu administrador.
            </p>

            <form onSubmit={handleLogin} noValidate className="space-y-5">
              <div>
                <label htmlFor="login-email" className="mb-2 block text-xs font-medium text-crema">
                  Correo electrónico
                </label>
                <div className="relative">
                  <Mail size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-subtle" />
                  <input
                    ref={emailRef}
                    id="login-email"
                    type="email"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      if (fieldErrors.email) setFieldErrors((current) => ({ ...current, email: undefined }));
                      clearError();
                    }}
                    placeholder="nombre@empresa.com"
                    autoComplete="email"
                    aria-invalid={Boolean(fieldErrors.email)}
                    aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
                    className={cn(INPUT_CLASS, fieldErrors.email && "border-red-400/70 focus:border-red-400 focus:ring-red-400/15")}
                  />
                </div>
                {fieldErrors.email ? (
                  <p id="login-email-error" className="mt-2 flex items-center gap-1.5 text-xs text-danger">
                    <AlertCircle size={12} aria-hidden="true" />
                    {fieldErrors.email}
                  </p>
                ) : null}
              </div>

              <div>
                <label htmlFor="login-password" className="mb-2 block text-xs font-medium text-crema">
                  Contraseña
                </label>
                <div className="relative">
                  <Lock size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-subtle" />
                  <input
                    ref={passwordRef}
                    id="login-password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(event) => {
                      setPassword(event.target.value);
                      if (fieldErrors.password) setFieldErrors((current) => ({ ...current, password: undefined }));
                      clearError();
                    }}
                    placeholder="Ingresa tu contraseña"
                    autoComplete="current-password"
                    aria-invalid={Boolean(fieldErrors.password)}
                    aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
                    className={cn(INPUT_CLASS, "pr-12", fieldErrors.password && "border-red-400/70 focus:border-red-400 focus:ring-red-400/15")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-subtle transition-colors hover:text-muted"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {fieldErrors.password ? (
                  <p id="login-password-error" className="mt-2 flex items-center gap-1.5 text-xs text-danger">
                    <AlertCircle size={12} aria-hidden="true" />
                    {fieldErrors.password}
                  </p>
                ) : null}
              </div>

              <div aria-live="polite" aria-atomic="true">
                {error ? <ErrorBanner message={error} /> : null}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex h-12 w-full items-center justify-center rounded-[0.8rem] bg-arcilla text-sm font-semibold text-on-accent transition-colors hover:bg-arcilla/90 focus-visible:ring-2 focus-visible:ring-arcilla/70 disabled:cursor-wait disabled:opacity-60"
              >
                {loading ? "Verificando acceso…" : "Iniciar sesión"}
              </button>
            </form>

            <p className="mt-7 text-center font-sans text-xs text-subtle">
              Acceso exclusivo para personal autorizado
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-[0.8rem] border border-danger/25 bg-danger/5 px-3.5 py-3 text-danger">
      <AlertCircle size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span className="text-xs leading-relaxed">{message}</span>
    </div>
  );
}
