import { apiClient } from "./client";
import type { Zone, ZoneCreateRequest } from "./types";

export const zonesApi = {
  create: (cameraId: string, body: ZoneCreateRequest) =>
    apiClient.post<Zone>(`/cameras/${cameraId}/zones`, body),
  list: (cameraId: string) => apiClient.get<Zone[]>(`/cameras/${cameraId}/zones`),
  remove: (zoneId: string) => apiClient.delete<void>(`/zones/${zoneId}`),
};
