"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  usersService,
  type CreateUserInput,
  type UpdateUserInput,
} from "@/services/users.service";

export const USER_KEYS = {
  all: ["users"] as const,
  list: ["users", "list"] as const,
};

export function useUsers() {
  return useQuery({
    queryKey: USER_KEYS.list,
    queryFn: () => usersService.list(),
    staleTime: 30_000,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateUserInput) => usersService.create(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USER_KEYS.all }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, input }: { userId: string; input: UpdateUserInput }) =>
      usersService.update(userId, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USER_KEYS.all }),
  });
}

export function useDeactivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersService.deactivate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USER_KEYS.all }),
  });
}

export function useChangeUserPassword() {
  return useMutation({
    mutationFn: ({ userId, password }: { userId: string; password: string }) =>
      usersService.changePassword(userId, password),
  });
}
