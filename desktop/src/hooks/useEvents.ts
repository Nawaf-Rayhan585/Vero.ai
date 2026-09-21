import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { eventsApi, type EventsQuery } from "../api/events";

const EVENTS_POLL_INTERVAL_MS = 5000;
const PAGE_SIZE = 50;

/**
 * Newest-first events, paged backwards with the API's cursor. Polls gently so new events
 * appear on their own; each poll refetches the pages already loaded, which stays cheap at
 * this page size and keeps the list consistent.
 */
export function useEvents(filters: Omit<EventsQuery, "before" | "limit">) {
  return useInfiniteQuery({
    queryKey: ["events", filters],
    queryFn: ({ pageParam }) => eventsApi.list({ ...filters, limit: PAGE_SIZE, before: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_before,
    refetchInterval: EVENTS_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}
