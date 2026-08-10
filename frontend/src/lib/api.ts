import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "",
  headers: { "Content-Type": "application/json" },
  // Enviar/recibir la cookie de sesión HttpOnly (C-5). El token ya no se lee por JS.
  withCredentials: true,
});

const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

api.interceptors.request.use((config) => {
  if (typeof document !== "undefined" && MUTATING_METHODS.has(config.method?.toLowerCase() ?? "")) {
    const csrfToken = document.cookie
      .split("; ")
      .find((entry) => entry.startsWith("csrf_token="))
      ?.split("=")[1];
    if (csrfToken) config.headers.set("X-CSRF-Token", decodeURIComponent(csrfToken));
  }
  return config;
});

// Refresh automático (C-14): ante un 401, intenta renovar el access token usando el
// refresh token (cookie HttpOnly) y reintenta la petición una sola vez. Si el refresh
// falla, redirige al login. Se comparte una única promesa para evitar refrescos en
// paralelo cuando varias peticiones fallan a la vez.
let refreshPromise: Promise<unknown> | null = null;

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const isAuthRoute = original?.url?.includes("/api/v1/auth/");

    if (status === 401 && original && !original._retry && !isAuthRoute) {
      original._retry = true;
      try {
        refreshPromise = refreshPromise ?? api.post("/api/v1/auth/refresh");
        await refreshPromise;
        refreshPromise = null;
        return api(original); // reintentar con la cookie renovada
      } catch (e) {
        refreshPromise = null;
        if (typeof window !== "undefined") window.location.href = "/login";
        return Promise.reject(e);
      }
    }

    if (status === 401 && typeof window !== "undefined" && !isAuthRoute) {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
