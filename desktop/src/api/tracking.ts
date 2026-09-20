import { apiClient } from "./client";
import { getApiBaseUrl } from "./config";
import type { TrackingStatus } from "./types";

export const trackingApi = {
  start: (cameraId: string) => apiClient.post<TrackingStatus>(`/cameras/${cameraId}/tracking/start`, undefined),
  stop: (cameraId: string) => apiClient.post<TrackingStatus>(`/cameras/${cameraId}/tracking/stop`, undefined),
  status: (cameraId: string) => apiClient.get<TrackingStatus>(`/cameras/${cameraId}/tracking/status`),
  latestFrameUrl: (cameraId: string, options: { heatmap?: boolean } = {}) =>
    `${getApiBaseUrl()}/cameras/${cameraId}/tracking/latest-frame${options.heatmap ? "?heatmap=true" : ""}`,
};
