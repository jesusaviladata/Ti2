"use client";

import { useState } from "react";
import { X, Server, Loader2, CheckCircle2, AlertCircle, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useDialog } from "@/hooks/useDialog";
import { useConnectionsStore } from "@/store/connections.store";
import type { SqlConnection, AuthMode, EncryptMode } from "@/types/connection";

interface Props {
  open:    boolean;
  onClose: () => void;
}

type Tab = "properties" | "string";

const AUTH_OPTIONS: { value: AuthMode; label: string }[] = [
  { value: "sql",     label: "Autenticación SQL Server" },
  { value: "windows", label: "Autenticación de Windows" },
];

const ENCRYPT_OPTIONS: { value: EncryptMode; label: string }[] = [
  { value: "Mandatory", label: "Mandatory" },
  { value: "Optional",  label: "Optional"  },
  { value: "Strict",    label: "Strict"    },
];

function buildConnString(
  server: string,
  authMode: AuthMode,
  username: string,
  password: string,
  database: string,
  encrypt: EncryptMode,
  trustCert: boolean
) {
  const parts = [
    `Server=${server || "localhost,1433"}`,
    authMode === "windows"
      ? "Integrated Security=True"
      : `User Id=${username};Password=***`,
    `Database=${database === "<default>" || !database ? "master" : database}`,
    `Encrypt=${encrypt}`,
    trustCert ? "TrustServerCertificate=True" : "",
  ].filter(Boolean);
  return parts.join(";");
}

export function SqlConnectionModal({ open, onClose }: Props) {
  const { addConnection, toPayload } = useConnectionsStore();

  const [tab,       setTab]       = useState<Tab>("properties");
  const [server,    setServer]    = useState("");
  const [authMode,  setAuthMode]  = useState<AuthMode>("sql");
  const [username,  setUsername]  = useState("sa");
  const [password,  setPassword]  = useState("");
  const [showPw,    setShowPw]    = useState(false);
  const [database,  setDatabase]  = useState("<default>");
  const [encrypt,   setEncrypt]   = useState<EncryptMode>("Mandatory");
  const [trustCert, setTrustCert] = useState(true);

  const [testing,   setTesting]   = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const dialogRef = useDialog(open, handleClose);

  if (!open) return null;

  const connString = buildConnString(server, authMode, username, password, database, encrypt, trustCert);

  async function handleTest() {
    if (!server.trim()) return;
    setTesting(true);
    setTestResult(null);
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
    try {
      const res = await fetch(`${apiBase}/api/v1/connections/test`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",   // enviar la cookie de sesión (el endpoint exige auth)
        body: JSON.stringify({
          server,
          username:   authMode === "sql" ? username : "",
          password:   authMode === "sql" ? password : "",
          encrypt:    encrypt.toLowerCase(),
          trust_cert: trustCert,
        }),
      });
      if (!res.ok && res.status !== 200) {
        setTestResult({ ok: false, message: `Backend respondió ${res.status} — ¿está corriendo dev_server.py?` });
        return;
      }
      const data = await res.json();
      if (data.connected) {
        const n = data.databases?.length ?? 0;
        setTestResult({ ok: true, message: `Conexión exitosa — ${n} base${n !== 1 ? "s" : ""} de datos encontrada${n !== 1 ? "s" : ""}` });
      } else {
        // Show the actual pyodbc error if available
        const msg = data.error
          ? `Error: ${data.error}`
          : "No se pudo conectar — verifica server, usuario y contraseña";
        setTestResult({ ok: false, message: msg });
      }
    } catch (err) {
      setTestResult({ ok: false, message: "No se pudo alcanzar el backend — ¿está corriendo dev_server.py?" });
    } finally {
      setTesting(false);
    }
  }

  function handleConnect() {
    if (!server.trim()) return;
    const conn: SqlConnection = {
      id:                    crypto.randomUUID(),
      label:                 server,
      server,
      authMode,
      username:              authMode === "sql" ? username : "",
      password:              authMode === "sql" ? password : "",
      database,
      encrypt,
      trustServerCertificate: trustCert,
      createdAt:             new Date().toISOString(),
    };
    addConnection(conn);
    onClose();
  }

  function handleClose() {
    setTestResult(null);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={handleClose} aria-hidden="true" />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sqlconn-title"
        className="relative z-10 w-full max-w-[480px] rounded-[1.5rem] bg-carbon border border-musgo/30 shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-musgo/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[0.65rem] bg-musgo/30 flex items-center justify-center">
              <Server size={15} className="text-crema/60" />
            </div>
            <div>
              <p className="font-mono text-xs text-arcilla uppercase tracking-widest mb-0.5">SQL Server</p>
              <h2 id="sqlconn-title" className="font-display text-xl italic font-light text-crema">
                Nueva conexión<span className="text-arcilla">.</span>
              </h2>
            </div>
          </div>
          <button onClick={handleClose} aria-label="Cerrar" className="text-crema/30 hover:text-crema transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-musgo/20">
          {(["properties", "string"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 py-2.5 font-mono text-xs tracking-wide transition-colors border-b-2 -mb-px",
                tab === t
                  ? "border-arcilla text-crema"
                  : "border-transparent text-crema/35 hover:text-crema/55"
              )}
            >
              {t === "properties" ? "Propiedades" : "Cadena de conexión"}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === "properties" ? (
            <div className="space-y-4">
              {/* Servidor */}
              <Field label="Servidor">
                <input
                  type="text"
                  value={server}
                  onChange={(e) => setServer(e.target.value)}
                  placeholder="host,1433  o  IP\\INSTANCIA"
                  className="field-input"
                />
              </Field>

              {/* Autenticación */}
              <Field label="Autenticación">
                <select
                  value={authMode}
                  onChange={(e) => setAuthMode(e.target.value as AuthMode)}
                  className="field-input"
                >
                  {AUTH_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </Field>

              {/* SQL auth fields */}
              {authMode === "sql" && (
                <>
                  <Field label="Usuario">
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="field-input"
                    />
                  </Field>

                  <Field label="Contraseña">
                    <div className="relative">
                      <input
                        type={showPw ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="field-input pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPw((v) => !v)}
                        aria-label={showPw ? "Ocultar contraseña" : "Mostrar contraseña"}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-crema/30 hover:text-crema/60 transition-colors"
                      >
                        {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </Field>
                </>
              )}

              {/* Base de datos */}
              <Field label="Base de datos">
                <input
                  type="text"
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  placeholder="<default>"
                  className="field-input"
                />
              </Field>

              {/* Cifrado */}
              <Field label="Cifrado">
                <select
                  value={encrypt}
                  onChange={(e) => setEncrypt(e.target.value as EncryptMode)}
                  className="field-input"
                >
                  {ENCRYPT_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <label className="flex items-center gap-2 mt-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={trustCert}
                    onChange={(e) => setTrustCert(e.target.checked)}
                    className="accent-arcilla"
                  />
                  <span className="font-mono text-[11px] text-crema/35">Confiar en el certificado del servidor</span>
                </label>
              </Field>

              {/* Test result */}
              {testResult && (
                <div className={cn(
                  "flex items-start gap-2.5 rounded-[0.75rem] border px-4 py-3 font-mono text-xs",
                  testResult.ok
                    ? "bg-green-900/10 border-green-800/30 text-green-400"
                    : "bg-red-900/10 border-red-800/30 text-red-400"
                )}>
                  {testResult.ok
                    ? <CheckCircle2 size={13} className="shrink-0 mt-0.5" />
                    : <AlertCircle  size={13} className="shrink-0 mt-0.5" />
                  }
                  {testResult.message}
                </div>
              )}
            </div>
          ) : (
            /* Connection String tab */
            <div className="rounded-[0.75rem] bg-musgo/10 border border-musgo/20 p-4">
              <p className="font-mono text-[11px] text-crema/50 leading-relaxed break-all select-all">
                {connString}
              </p>
              <p className="font-mono text-[10px] text-crema/20 mt-3">
                (La contraseña se oculta — se guardará de forma segura en el almacén local)
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-musgo/15">
            <Button
              variant="ghost"
              type="button"
              onClick={handleTest}
              disabled={!server.trim() || testing}
              className="text-xs"
            >
              {testing
                ? <><Loader2 size={12} className="animate-spin mr-1.5" />Probando…</>
                : "Probar conexión"
              }
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" type="button" onClick={handleClose}>
                Cancelar
              </Button>
              <Button
                type="button"
                onClick={handleConnect}
                disabled={!server.trim() || (authMode === "sql" && !username.trim())}
              >
                Conectar
              </Button>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        .field-input {
          width: 100%;
          height: 2.5rem;
          background: rgb(46 64 54 / 0.1);
          border: 1px solid rgb(46 64 54 / 0.3);
          border-radius: 0.75rem;
          padding: 0 1rem;
          font-family: var(--font-mono);
          font-size: 0.75rem;
          color: rgb(242 240 233 / 0.8);
          transition: border-color 0.15s;
          outline: none;
        }
        .field-input:focus {
          border-color: rgb(204 88 51 / 0.5);
        }
        .field-input option {
          background: #1A1A1A;
        }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="font-mono text-[11px] text-crema/40 uppercase tracking-wider block mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}
