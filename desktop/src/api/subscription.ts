import { apiClient } from "./client";
import type { PayPalCheckoutResponse, Subscription, SubscriptionUpdateRequest } from "./types";

export const subscriptionApi = {
  get: () => apiClient.get<Subscription>("/subscription"),
  update: (body: SubscriptionUpdateRequest) => apiClient.patch<Subscription>("/subscription", body),
  startPayPalCheckout: () => apiClient.post<PayPalCheckoutResponse>("/subscription/paypal/checkout", {}),
  syncPayPalSubscription: () => apiClient.post<Subscription>("/subscription/paypal/sync", {}),
  cancelPayPalSubscription: () => apiClient.post<Subscription>("/subscription/paypal/cancel", {}),
};
