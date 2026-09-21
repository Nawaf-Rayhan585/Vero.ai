import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi, type HeatmapQuery } from "../api/analytics";

export interface HeatmapImage {
  url: string;
  /** Whether the heat was drawn over a fresh camera snapshot or a plain background. */
  background: "snapshot" | "neutral";
  samples: number;
}

interface FetchedHeatmap {
  blob: Blob;
  background: "snapshot" | "neutral";
  samples: number;
}

async function fetchHeatmap(url: string): Promise<FetchedHeatmap> {
  // fetch() rather than <img src>, for the same reason as the live feeds (see
  // useImageBlobUrl): a cross-origin <img> silently swallows a JSON error body.
  const response = await fetch(url);
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail as string | undefined)
      .catch(() => undefined);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return {
    blob: await response.blob(),
    background: response.headers.get("X-Heatmap-Background") === "snapshot" ? "snapshot" : "neutral",
    samples: Number(response.headers.get("X-Heatmap-Samples") ?? 0),
  };
}

/** The saved heatmap picture for a camera and range. Not polled: rendering it grabs a live
 * snapshot from the camera, which is not something to do every few seconds. */
export function useHeatmapImage(query: HeatmapQuery | null) {
  const url = query ? analyticsApi.heatmapUrl(query) : null;
  const fetched = useQuery({
    queryKey: ["analytics", "heatmap-image", url],
    queryFn: () => fetchHeatmap(url as string),
    enabled: url !== null,
    retry: false,
    staleTime: 60_000,
  });

  const [image, setImage] = useState<HeatmapImage | null>(null);
  useEffect(() => {
    if (!fetched.data) {
      setImage(null);
      return;
    }
    const objectUrl = URL.createObjectURL(fetched.data.blob);
    setImage({ url: objectUrl, background: fetched.data.background, samples: fetched.data.samples });
    return () => URL.revokeObjectURL(objectUrl);
  }, [fetched.data]);

  return { image, isLoading: fetched.isLoading, error: fetched.error as Error | null };
}
