import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { subscriptionApi } from "../api/subscription";
import type { SubscriptionUpdateRequest } from "../api/types";

/** Computed client-side from the server-supplied `trial_ends_at`, so it's always exactly
 * as current as the clock, not just as current as the last fetch. Shared by TopBar's
 * indicator and SubscriptionPage's countdown. */
export function daysRemaining(trialEndsAt: string): number {
  const ms = new Date(trialEndsAt).getTime() - Date.now();
  return Math.ceil(ms / (24 * 60 * 60 * 1000));
}

export function useSubscription() {
  return useQuery({
    queryKey: ["subscription"],
    queryFn: subscriptionApi.get,
  });
}

export function useUpdateSubscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SubscriptionUpdateRequest) => subscriptionApi.update(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscription"] }),
  });
}
