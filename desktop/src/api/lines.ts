import { apiClient } from "./client";
import type { Line, LineCreateRequest } from "./types";

export const linesApi = {
  create: (cameraId: string, body: LineCreateRequest) =>
    apiClient.post<Line>(`/cameras/${cameraId}/lines`, body),
  list: (cameraId: string) => apiClient.get<Line[]>(`/cameras/${cameraId}/lines`),
  remove: (lineId: string) => apiClient.delete<void>(`/lines/${lineId}`),
};
