"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth.store";
import api from "@/lib/api";
import type { User } from "@/types";



export function useAuth() {
  const { user, isAuthenticated, setAuth, clearAuth } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const queryClient = useQueryClient();

  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ username: email, password });
        await api.post("/api/v1/auth/login", params, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
        });

        await _persistAndRedirect(setAuth, router);
      } catch (err: any) {
        const msg = err.response?.data?.detail ?? "Error al iniciar sesión";
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [setAuth, router]
  );

  const logout = useCallback(async () => {
    // El backend limpia las cookies HttpOnly (access + refresh) en /logout.
    try {
      await api.post("/api/v1/auth/logout");
    } catch (err) {
      console.error("No se pudo confirmar el cierre de sesión remoto", err);
    }
    clearAuth();
    queryClient.clear();
    router.push("/login");
  }, [clearAuth, queryClient, router]);

  return { user, isAuthenticated, loading, error, login, logout };
}

async function _persistAndRedirect(
  setAuth: (user: User) => void,
  router: ReturnType<typeof useRouter>
) {
  // La cookie de sesión (HttpOnly) ya la fijó el backend en la respuesta de login.
  // Aquí solo obtenemos el perfil del usuario para el estado del cliente.
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
