import { apiClient } from "./client";
import { getApiBaseUrl } from "./config";
import type { Camera, CameraCreateRequest, CameraUpdateRequest } from "./types";

export const camerasApi = {
  create: (body: CameraCreateRequest) => apiClient.post<Camera>("/cameras", body),
  get: (id: string) => apiClient.get<Camera>(`/cameras/${id}`),
  list: () => apiClient.get<Camera[]>("/cameras"),
  update: (id: string, body: CameraUpdateRequest) => apiClient.patch<Camera>(`/cameras/${id}`, body),
  remove: (id: string) => apiClient.delete<void>(`/cameras/${id}`),
  testConnection: (id: string) => apiClient.post<Camera>(`/cameras/${id}/test-connection`, undefined),
  snapshotUrl: (id: string) => `${getApiBaseUrl()}/cameras/${id}/snapshot`,
};
