import { apiClient } from "./client";

export interface HealthStatus {
  status: string;
}

export const healthApi = {
  health: () => apiClient.get<HealthStatus>("/health"),
  healthDb: () => apiClient.get<HealthStatus>("/health/db"),
};
