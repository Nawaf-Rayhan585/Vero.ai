import { apiClient } from "./client";
import type { Subscription, SubscriptionUpdateRequest } from "./types";

export const subscriptionApi = {
  get: () => apiClient.get<Subscription>("/subscription"),
  update: (body: SubscriptionUpdateRequest) => apiClient.patch<Subscription>("/subscription", body),
};
