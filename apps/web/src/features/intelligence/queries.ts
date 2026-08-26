"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { listIntelligenceIntegrations, normalizeIntelligenceIntegration } from "@/lib/api/intelligence";
import { queryKeys } from "@/lib/query/keys";

export function useIntelligenceIntegrations() {
  return useQuery({
    queryKey: queryKeys.intelligence.integrations,
    queryFn: listIntelligenceIntegrations,
  });
}

export function useNormalizeIntelligenceIntegration() {
  return useMutation({ mutationFn: normalizeIntelligenceIntegration });
}
