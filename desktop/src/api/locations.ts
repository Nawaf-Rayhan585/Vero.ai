import { apiClient } from "./client";
import type { Location, LocationCreateRequest, LocationUpdateRequest } from "./types";

export const locationsApi = {
  list: () => apiClient.get<Location[]>("/locations"),
  create: (body: LocationCreateRequest) => apiClient.post<Location>("/locations", body),
  update: (id: string, body: LocationUpdateRequest) => apiClient.patch<Location>(`/locations/${id}`, body),
  remove: (id: string) => apiClient.delete<void>(`/locations/${id}`),
};
