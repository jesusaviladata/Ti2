"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import axios from "axios";
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Power,
  PowerOff,
  ShieldCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDialog } from "@/hooks/useDialog";
import {
  useChangeUserPassword,
  useCreateUser,
  useDeactivateUser,
  useUpdateUser,
  useUsers,
} from "@/hooks/useUsers";
import { useAuthStore } from "@/store/auth.store";
import type { User, UserRole } from "@/types";
import type { CreateUserInput } from "@/services/users.service";
import { cn } from "@/lib/utils";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const USERNAME_PATTERN = /^[a-zA-Z0-9._-]+$/;
const INPUT =
  "w-full h-11 rounded-[0.75rem] border border-musgo/35 bg-carbon/55 px-3.5 text-sm text-crema placeholder:text-crema/25 outline-none transition-colors focus:border-arcilla/70 focus:ring-1 focus:ring-arcilla/30";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrador",
  supervisor: "Supervisor",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_OPTIONS = Object.entries(ROLE_LABELS) as [UserRole, string][];

type Notice = { kind: "success" | "error"; message: string } | null;

function errorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return fallback;
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (!error.response) return "No fue posible conectar con el servicio.";
  return fallback;
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-crema/70">{label}</span>
      {children}
      {error ? <span className="block text-xs text-red-300">{error}</span> : null}
    </label>
  );
}

function ModalFrame({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useDialog(true, onClose);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-carbon/80 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-dialog-title"
        aria-describedby="user-dialog-description"
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-[1.25rem] border border-musgo/35 bg-carbon shadow-2xl"
      >
        <div className="flex items-start justify-between border-b border-musgo/20 px-6 py-5">
          <div>
            <h2 id="user-dialog-title" className="text-lg font-semibold text-crema">{title}</h2>
            <p id="user-dialog-description" className="mt-1 text-xs leading-relaxed text-crema/45">{description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="flex h-8 w-8 items-center justify-center rounded-[0.65rem] text-crema/35 transition-colors hover:bg-musgo/20 hover:text-crema"
          >
            <X size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CreateUserModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (input: CreateUserInput) => Promise<void>;
}) {
  const [form, setForm] = useState<CreateUserInput>({
    full_name: "",
    email: "",
    username: "",
    password: "",
    role: "technician",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof CreateUserInput>(key: K, value: CreateUserInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: "" }));
    setServerError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (form.full_name.trim().length < 2) nextErrors.full_name = "Ingresa el nombre completo.";
    if (!EMAIL_PATTERN.test(form.email.trim())) nextErrors.email = "Ingresa un correo electrónico válido.";
    if (form.username.trim().length < 3 || !USERNAME_PATTERN.test(form.username.trim())) {
      nextErrors.username = "Usa al menos 3 caracteres: letras, números, punto, guion o guion bajo.";
    }
    if (form.password.length < 14) nextErrors.password = "La contraseña debe tener al menos 14 caracteres.";

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setSubmitting(true);
    try {
      await onCreate({
        ...form,
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        username: form.username.trim(),
      });
    } catch (error) {
      setServerError(errorMessage(error, "No fue posible crear el usuario."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalFrame
      title="Nuevo usuario"
      description="Crea una cuenta dentro de tu organización y asigna solamente los permisos necesarios."
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="space-y-4 p-6">
        <Field label="Nombre completo" error={errors.full_name}>
          <input
            value={form.full_name}
            onChange={(event) => update("full_name", event.target.value)}
            className={cn(INPUT, errors.full_name && "border-red-400/70")}
            aria-invalid={Boolean(errors.full_name)}
            autoComplete="name"
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Correo electrónico" error={errors.email}>
            <input
              type="email"
              value={form.email}
              onChange={(event) => update("email", event.target.value)}
              className={cn(INPUT, errors.email && "border-red-400/70")}
              aria-invalid={Boolean(errors.email)}
              autoComplete="email"
            />
          </Field>
          <Field label="Usuario" error={errors.username}>
            <input
              value={form.username}
              onChange={(event) => update("username", event.target.value)}
              className={cn(INPUT, errors.username && "border-red-400/70")}
              aria-invalid={Boolean(errors.username)}
              autoComplete="username"
            />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Contraseña temporal" error={errors.password}>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={form.password}
                onChange={(event) => update("password", event.target.value)}
                className={cn(INPUT, "pr-11", errors.password && "border-red-400/70")}
                aria-invalid={Boolean(errors.password)}
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-crema/35 hover:text-crema/70"
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </Field>
          <Field label="Rol">
            <select
              value={form.role}
              onChange={(event) => update("role", event.target.value as UserRole)}
              className={INPUT}
            >
              {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </Field>
        </div>

        {serverError ? (
          <div role="alert" className="flex items-start gap-2 rounded-[0.75rem] border border-red-400/25 bg-red-950/20 px-3.5 py-3 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            {serverError}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 border-t border-musgo/15 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? <Loader2 size={15} className="mr-2 animate-spin" /> : <UserPlus size={15} className="mr-2" />}
            Crear usuario
          </Button>
        </div>
      </form>
    </ModalFrame>
  );
}

function PasswordModal({
  user,
  onClose,
  onSave,
}: {
  user: User;
  onClose: () => void;
  onSave: (password: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < 14) {
      setError("La contraseña debe tener al menos 14 caracteres.");
      return;
    }
    if (password !== confirmation) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSave(password);
    } catch (requestError) {
      setError(errorMessage(requestError, "No fue posible cambiar la contraseña."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalFrame
      title="Restablecer contraseña"
      description={`Define una contraseña temporal para ${user.fullName}.`}
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate className="space-y-4 p-6">
        <Field label="Nueva contraseña">
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => { setPassword(event.target.value); setError(null); }}
              className={cn(INPUT, "pr-11", error && "border-red-400/70")}
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-crema/35 hover:text-crema/70"
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </Field>
        <Field label="Confirmar contraseña">
          <input
            type="password"
            value={confirmation}
            onChange={(event) => { setConfirmation(event.target.value); setError(null); }}
            className={cn(INPUT, error && "border-red-400/70")}
            autoComplete="new-password"
          />
        </Field>
        {error ? (
          <div role="alert" className="flex items-start gap-2 rounded-[0.75rem] border border-red-400/25 bg-red-950/20 px-3.5 py-3 text-xs text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            {error}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-musgo/15 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? <Loader2 size={15} className="mr-2 animate-spin" /> : <KeyRound size={15} className="mr-2" />}
            Guardar contraseña
          </Button>
        </div>
      </form>
    </ModalFrame>
  );
}

export function UsersAdmin() {
  const currentUser = useAuthStore((state) => state.user);
  const usersQuery = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const deactivateUser = useDeactivateUser();
  const changePassword = useChangeUserPassword();
  const [createOpen, setCreateOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<User | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const users = usersQuery.data?.items ?? [];

  async function create(input: CreateUserInput) {
    await createUser.mutateAsync(input);
    setCreateOpen(false);
    setNotice({ kind: "success", message: "Usuario creado correctamente." });
  }

  async function changeRole(user: User, role: UserRole) {
    setNotice(null);
    try {
      await updateUser.mutateAsync({ userId: user.id, input: { role } });
      setNotice({ kind: "success", message: `Rol de ${user.fullName} actualizado.` });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "No fue posible cambiar el rol.") });
    }
  }

  async function activate(user: User) {
    setNotice(null);
    try {
      await updateUser.mutateAsync({ userId: user.id, input: { is_active: true } });
      setNotice({ kind: "success", message: `${user.fullName} fue activado.` });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "No fue posible activar el usuario.") });
    }
  }

  async function confirmDeactivate() {
    if (!deactivateTarget) return;
    const user = deactivateTarget;
    setDeactivateTarget(null);
    setNotice(null);
    try {
      await deactivateUser.mutateAsync(user.id);
      setNotice({ kind: "success", message: `${user.fullName} fue desactivado.` });
    } catch (error) {
      setNotice({ kind: "error", message: errorMessage(error, "No fue posible desactivar el usuario.") });
    }
  }

  async function savePassword(password: string) {
    if (!passwordUser) return;
    const name = passwordUser.fullName;
    await changePassword.mutateAsync({ userId: passwordUser.id, password });
    setPasswordUser(null);
    setNotice({ kind: "success", message: `Contraseña de ${name} actualizada.` });
  }

  return (
    <section className="space-y-4" aria-labelledby="users-title">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={15} className="text-arcilla" />
            <h2 id="users-title" className="text-base font-semibold text-crema">Usuarios</h2>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-crema/45">
            Administra el acceso del personal de tu organización. Las cuentas no se registran desde el login.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <UserPlus size={14} className="mr-2" />
          Nuevo usuario
        </Button>
      </div>

      {notice ? (
        <div
          role={notice.kind === "error" ? "alert" : "status"}
          className={cn(
            "flex items-start gap-2 rounded-[0.75rem] border px-3.5 py-3 text-xs",
            notice.kind === "error"
              ? "border-red-400/25 bg-red-950/20 text-red-200"
              : "border-emerald-400/20 bg-emerald-950/15 text-emerald-200",
          )}
        >
          {notice.kind === "error" ? <AlertCircle size={14} /> : <CheckCircle2 size={14} />}
          <span>{notice.message}</span>
        </div>
      ) : null}

      <div className="overflow-hidden rounded-[1rem] border border-musgo/25 bg-musgo/[0.06]">
        {usersQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 px-5 py-12 text-xs text-crema/40">
            <Loader2 size={15} className="animate-spin" />
            Cargando usuarios…
          </div>
        ) : usersQuery.isError ? (
          <div role="alert" className="px-5 py-10 text-center text-sm text-red-300">
            No fue posible cargar los usuarios.
          </div>
        ) : users.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Users size={24} className="mx-auto text-crema/20" />
            <p className="mt-2 text-sm text-crema/45">Todavía no hay usuarios.</p>
          </div>
        ) : (
          <div className="divide-y divide-musgo/15">
            {users.map((user) => {
              const isSelf = user.id === currentUser?.id;
              const initials = user.fullName.split(" ").map((part) => part[0]).slice(0, 2).join("").toUpperCase();
              const busy =
                (updateUser.isPending && updateUser.variables?.userId === user.id) ||
                (deactivateUser.isPending && deactivateUser.variables === user.id);

              return (
                <article key={user.id} className="grid gap-4 px-4 py-4 lg:grid-cols-[minmax(220px,1fr)_170px_110px_auto] lg:items-center">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[0.7rem] border border-arcilla/20 bg-arcilla/10 font-mono text-xs text-arcilla">
                      {initials}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-crema">
                        {user.fullName}{isSelf ? <span className="ml-2 text-[10px] font-normal text-arcilla">Tú</span> : null}
                      </p>
                      <p className="truncate text-xs text-crema/40">{user.email} · @{user.username}</p>
                    </div>
                  </div>

                  <select
                    value={user.role}
                    onChange={(event) => changeRole(user, event.target.value as UserRole)}
                    disabled={isSelf || busy}
                    aria-label={`Rol de ${user.fullName}`}
                    className="h-9 rounded-[0.65rem] border border-musgo/30 bg-carbon/60 px-3 text-xs text-crema/75 outline-none focus:border-arcilla/60 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>

                  <span className={cn(
                    "inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px]",
                    user.isActive
                      ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-300"
                      : "border-crema/10 bg-crema/5 text-crema/40",
                  )}>
                    <span className={cn("h-1.5 w-1.5 rounded-full", user.isActive ? "bg-emerald-400" : "bg-crema/30")} />
                    {user.isActive ? "Activo" : "Inactivo"}
                  </span>

                  <div className="flex flex-wrap items-center justify-start gap-1.5 lg:justify-end">
                    <button
                      type="button"
                      onClick={() => setPasswordUser(user)}
                      className="flex h-9 items-center gap-1.5 rounded-[0.65rem] px-2.5 text-xs text-crema/50 transition-colors hover:bg-musgo/20 hover:text-crema"
                    >
                      <KeyRound size={13} />
                      Contraseña
                    </button>
                    {user.isActive ? (
                      <button
                        type="button"
                        onClick={() => setDeactivateTarget(user)}
                        disabled={isSelf || busy}
                        className="flex h-9 items-center gap-1.5 rounded-[0.65rem] px-2.5 text-xs text-red-300/70 transition-colors hover:bg-red-950/25 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <PowerOff size={13} />
                        Desactivar
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => activate(user)}
                        disabled={busy}
                        className="flex h-9 items-center gap-1.5 rounded-[0.65rem] px-2.5 text-xs text-emerald-300/70 transition-colors hover:bg-emerald-950/20 hover:text-emerald-300 disabled:opacity-30"
                      >
                        <Power size={13} />
                        Activar
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {createOpen ? <CreateUserModal onClose={() => setCreateOpen(false)} onCreate={create} /> : null}
      {passwordUser ? (
        <PasswordModal user={passwordUser} onClose={() => setPasswordUser(null)} onSave={savePassword} />
      ) : null}
      <ConfirmDialog
        open={Boolean(deactivateTarget)}
        title="Desactivar usuario"
        message={`La cuenta de ${deactivateTarget?.fullName ?? "este usuario"} perderá acceso hasta que la reactives.`}
        confirmLabel="Desactivar"
        danger
        onConfirm={confirmDeactivate}
        onCancel={() => setDeactivateTarget(null)}
      />
    </section>
  );
}
