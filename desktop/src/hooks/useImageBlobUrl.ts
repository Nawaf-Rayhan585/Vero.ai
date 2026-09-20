import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

async function fetchAsObjectUrl(url: string): Promise<string> {
  // A plain <img src=url> would make a no-cors request, and Chromium's Opaque Response
  // Blocking silently drops non-image error bodies for those — the <img> never fires
  // onError, so a broken/offline source would show nothing at all, forever. fetch() (a
  // normal CORS-mode request our CORSMiddleware already allows) sidesteps ORB entirely
  // and lets us read the real error detail on failure. Confirmed empirically against a
  // genuinely unreachable camera: onError never fired via <img>, but this does.
  const response = await fetch(url);
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail as string | undefined)
      .catch(() => undefined);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

/** Polls `url` and exposes each response as an object URL, revoking the previous one
 * so repeated polling doesn't leak blob handles. Used for both the raw camera snapshot
 * and the AI-annotated tracking frame — same ORB problem, same fix, same endpoint shape
 * (an image on success, a JSON error on failure). */
export function useImageBlobUrl(url: string | null, refetchIntervalMs: number) {
  const previousUrlRef = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ["image-blob", url],
    queryFn: () => fetchAsObjectUrl(url as string),
    enabled: url !== null,
    refetchInterval: refetchIntervalMs,
    retry: false,
  });

  useEffect(() => {
    const newUrl = query.data;
    const oldUrl = previousUrlRef.current;
    if (newUrl && newUrl !== oldUrl) {
      if (oldUrl) URL.revokeObjectURL(oldUrl);
      previousUrlRef.current = newUrl;
    }
  }, [query.data]);

  // Separate from the effect above: this also covers switching to a `url` that never
  // successfully resolves (e.g. an always-erroring camera), which would otherwise leave
  // the previous url's object URL alive until the whole component unmounts.
  useEffect(() => {
    return () => {
      if (previousUrlRef.current) {
        URL.revokeObjectURL(previousUrlRef.current);
        previousUrlRef.current = null;
      }
    };
  }, [url]);

  return query;
}
