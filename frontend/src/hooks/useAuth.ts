"use client";

import { useCallback, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import { authService } from "@/services/auth.service";
import api from "@/lib/api";
import type { User } from "@/types";

export function getLoginErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error) || !error.response) {
    return "El servicio no está disponible en este momento. Inténtalo nuevamente.";
  }

  const status = error.response.status;
  const detail = error.response.data?.detail;

  if (status === 401) return "Correo o contraseña incorrectos.";
  if (status === 403) {
    return detail === "Cuenta desactivada"
      ? "Tu cuenta está desactivada. Contacta a un administrador."
      : "No fue posible autorizar el inicio de sesión.";
  }
  if (status === 429) {
    return "Demasiados intentos. Espera unos minutos e inténtalo nuevamente.";
  }
  if (status >= 500) {
    return "El servicio no está disponible en este momento. Inténtalo nuevamente.";
  }
  return "No fue posible iniciar sesión. Inténtalo nuevamente.";
}

export function useAuth() {
  const { user, isAuthenticated, setAuth, clearAuth } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const queryClient = useQueryClient();

  const clearError = useCallback(() => setError(null), []);

  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      setLoading(true);
      setError(null);
      try {
        await authService.login(email.trim().toLowerCase(), password);
        await persistAndRedirect(setAuth, router);
      } catch (requestError) {
        setError(getLoginErrorMessage(requestError));
        throw requestError;
      } finally {
        setLoading(false);
      }
    },
    [setAuth, router],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch (requestError) {
      console.error("No se pudo confirmar el cierre de sesión remoto", requestError);
    }
    clearAuth();
    queryClient.clear();
    router.push("/login");
  }, [clearAuth, queryClient, router]);

  return { user, isAuthenticated, loading, error, clearError, login, logout };
}

async function persistAndRedirect(
  setAuth: (user: User) => void,
  router: ReturnType<typeof useRouter>,
) {
  const { data: me } = await api.get("/api/v1/auth/me");

  const user: User = {
    id: me.id,
    tenantId: me.tenantId,
    email: me.email,
    username: me.username,
    fullName: me.fullName,
    role: me.role,
    isActive: me.isActive,
  };

  setAuth(user);
  router.push("/dashboard");
}
