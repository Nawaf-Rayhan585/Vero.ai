import { trackingApi } from "../api/tracking";
import { useImageBlobUrl } from "./useImageBlobUrl";

const REFRESH_INTERVAL_MS = 1000;

export function useTrackingFrame(cameraId: string | null) {
  return useImageBlobUrl(cameraId ? trackingApi.latestFrameUrl(cameraId) : null, REFRESH_INTERVAL_MS);
}
