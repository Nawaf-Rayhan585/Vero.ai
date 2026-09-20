import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "../api/jobs";
import type { JobStatus } from "../api/types";

const POLL_INTERVAL_MS = 1500;
const ACTIVE_STATUSES: JobStatus[] = ["pending", "running"];

export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => jobsApi.get(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ACTIVE_STATUSES.includes(status) ? POLL_INTERVAL_MS : false;
    },
  });
}
