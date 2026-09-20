import { trackingApi } from "../api/tracking";
import { useImageBlobUrl } from "./useImageBlobUrl";

const REFRESH_INTERVAL_MS = 1000;

/** `heatmap` swaps to the same annotated frame with the accumulated heat overlay blended
 * on by the backend — a different URL, so React Query treats it as its own feed. */
export function useTrackingFrame(cameraId: string | null, heatmap = false) {
  return useImageBlobUrl(cameraId ? trackingApi.latestFrameUrl(cameraId, { heatmap }) : null, REFRESH_INTERVAL_MS);
}
