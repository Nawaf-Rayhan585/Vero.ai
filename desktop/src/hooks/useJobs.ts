import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "../api/jobs";

/** No interval polling: GET /jobs returns every job's full result payload
 * (can be ~100KB+ for a long video — see docs/ROADMAP.md). Refetches on
 * mount/focus and whenever the caller invalidates ["jobs"]. */
export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: jobsApi.list,
  });
}
