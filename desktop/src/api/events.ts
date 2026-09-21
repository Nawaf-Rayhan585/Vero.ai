import { apiClient } from "./client";
import type { EventList, EventType } from "./types";

export interface EventsQuery {
  camera_id?: string;
  /** Any of these types (the backend accepts the parameter more than once). */
  event_type?: EventType[];
  since?: string;
  until?: string;
  limit?: number;
  before?: string | null;
}

export function toQueryString(params: Record<string, string | number | string[] | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.append(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const eventsApi = {
  list: (query: EventsQuery = {}) => apiClient.get<EventList>(`/events${toQueryString({ ...query })}`),
};
