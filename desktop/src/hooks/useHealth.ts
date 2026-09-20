import { useQuery } from "@tanstack/react-query";
import { healthApi } from "../api/health";

const POLL_INTERVAL_MS = 10_000;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: healthApi.health,
    retry: false,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useHealthDb() {
  return useQuery({
    queryKey: ["health", "db"],
    queryFn: healthApi.healthDb,
    retry: false,
    refetchInterval: POLL_INTERVAL_MS,
  });
}
