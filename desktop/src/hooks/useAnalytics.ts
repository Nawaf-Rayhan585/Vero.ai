import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  analyticsApi,
  type HeatmapQuery,
  type RangeQuery,
  type TimeseriesQuery,
} from "../api/analytics";

const ANALYTICS_POLL_INTERVAL_MS = 10_000;

// keepPreviousData: while a new slice loads, the previous render stays on screen (the page
// dims it) instead of collapsing to a skeleton and jumping.

export function useAnalyticsSummary(query: RangeQuery | null) {
  return useQuery({
    queryKey: ["analytics", "summary", query],
    queryFn: () => analyticsApi.summary(query as RangeQuery),
    enabled: query !== null,
    refetchInterval: ANALYTICS_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}

export function useAnalyticsTimeseries(query: TimeseriesQuery | null) {
  return useQuery({
    queryKey: ["analytics", "timeseries", query],
    queryFn: () => analyticsApi.timeseries(query as TimeseriesQuery),
    enabled: query !== null,
    refetchInterval: ANALYTICS_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}

export function useHeatmapInfo(query: HeatmapQuery | null) {
  return useQuery({
    queryKey: ["analytics", "heatmap-info", query],
    queryFn: () => analyticsApi.heatmapInfo(query as HeatmapQuery),
    enabled: query !== null,
    refetchInterval: ANALYTICS_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}
