import api from "@/lib/api";
import type { User, UserRole } from "@/types";

export interface UserListResponse {
  items: User[];
  total: number;
  skip: number;
  limit: number;
}

export interface CreateUserInput {
  email: string;
  username: string;
  password: string;
  full_name: string;
  role: UserRole;
}

export interface UpdateUserInput {
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
}

export const usersService = {
  async list(skip = 0, limit = 100) {
    const { data } = await api.get<UserListResponse>("/api/v1/users", {
      params: { skip, limit },
    });
    return data;
  },

  async create(input: CreateUserInput) {
    const { data } = await api.post<User>("/api/v1/users", input);
    return data;
  },

  async update(userId: string, input: UpdateUserInput) {
    const { data } = await api.put<User>(`/api/v1/users/${userId}`, input);
    return data;
  },

  async deactivate(userId: string) {
    await api.delete(`/api/v1/users/${userId}`);
  },

  async changePassword(userId: string, newPassword: string) {
    await api.post(`/api/v1/users/${userId}/change-password`, {
      new_password: newPassword,
    });
  },
};
