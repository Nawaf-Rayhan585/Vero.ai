import { camerasApi } from "../api/cameras";
import { useImageBlobUrl } from "./useImageBlobUrl";

const REFRESH_INTERVAL_MS = 3000;

export function useCameraSnapshot(cameraId: string | null) {
  return useImageBlobUrl(cameraId ? camerasApi.snapshotUrl(cameraId) : null, REFRESH_INTERVAL_MS);
}
