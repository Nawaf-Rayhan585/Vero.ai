import { apiClient } from "./client";
import { toQueryString } from "./events";
import { getApiBaseUrl } from "./config";
import type { AnalyticsSummary, HeatmapInfo, Timeseries } from "./types";

export interface RangeQuery {
  since: string;
  until?: string;
  camera_id?: string;
}

export interface TimeseriesQuery extends RangeQuery {
  bucket: "hour" | "day";
  /** IANA time zone the buckets are cut in (the browser's own). */
  tz: string;
}

export interface HeatmapQuery {
  camera_id: string;
  since: string;
  until?: string;
}

export const analyticsApi = {
  summary: (query: RangeQuery) => apiClient.get<AnalyticsSummary>(`/analytics/summary${toQueryString({ ...query })}`),
  timeseries: (query: TimeseriesQuery) =>
    apiClient.get<Timeseries>(`/analytics/timeseries${toQueryString({ ...query })}`),
  heatmapInfo: (query: HeatmapQuery) =>
    apiClient.get<HeatmapInfo>(`/analytics/heatmap/info${toQueryString({ ...query })}`),
  heatmapUrl: (query: HeatmapQuery) => `${getApiBaseUrl()}/analytics/heatmap${toQueryString({ ...query })}`,
};
