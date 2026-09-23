import { apiClient } from "./client";
import type { Device, DeviceCreateRequest, DeviceUpdateRequest } from "./types";

export const devicesApi = {
  list: () => apiClient.get<Device[]>("/devices"),
  create: (body: DeviceCreateRequest) => apiClient.post<Device>("/devices", body),
  update: (id: string, body: DeviceUpdateRequest) => apiClient.patch<Device>(`/devices/${id}`, body),
  remove: (id: string) => apiClient.delete<void>(`/devices/${id}`),
};
