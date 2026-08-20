"use client";

import { useMutation } from "@tanstack/react-query";
import { agentCleanupService } from "@/services/agent-cleanup.service";

export function useSimulateAgentCleanup() {
  return useMutation({ mutationFn: agentCleanupService.simulate });
}

export function useExecuteAgentCleanup() {
  return useMutation({ mutationFn: agentCleanupService.execute });
}
