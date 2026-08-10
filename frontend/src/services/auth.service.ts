import api from "@/lib/api";

export const authService = {
  async login(email: string, password: string) {
    const params = new URLSearchParams({ username: email, password });
    const { data } = await api.post<{ authenticated: boolean }>(
      "/api/v1/auth/login",
      params,
      { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
    );
    return data;
  },

  async refresh() {
    await api.post("/api/v1/auth/refresh");
  },

  async logout() {
    await api.post("/api/v1/auth/logout");
  },
};
