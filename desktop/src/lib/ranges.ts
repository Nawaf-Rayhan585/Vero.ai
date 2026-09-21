export type AnalyticsPreset = "today" | "7d" | "30d";
export type EventsPreset = "all" | "today" | "7d";

export const ANALYTICS_PRESETS: { id: AnalyticsPreset; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
];

export const EVENTS_PRESETS: { id: EventsPreset; label: string }[] = [
  { id: "all", label: "All time" },
  { id: "today", label: "Today" },
  { id: "7d", label: "Last 7 days" },
];

export interface AnalyticsRange {
  since: string;
  until: string;
  bucket: "hour" | "day";
}

/** The browser's own IANA time zone, which is what "today" means to whoever is looking. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

// Local-time arithmetic through the Date constructor, so daylight-saving days come out right.
export function startOfLocalDay(moment: Date, offsetDays = 0): Date {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate() + offsetDays);
}

/**
 * The range for an analytics preset. The end is deliberately a stable boundary (the next
 * local hour, or tomorrow's midnight) rather than "right now": it doesn't change on every
 * render, so the query isn't refetched and re-keyed constantly. Whatever part of the final
 * bucket is still in the future simply has no data yet, and the backend only credits
 * tracked time up to the present.
 */
export function analyticsRange(preset: AnalyticsPreset, now: Date = new Date()): AnalyticsRange {
  if (preset === "today") {
    const nextHour = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours() + 1);
    return { since: startOfLocalDay(now).toISOString(), until: nextHour.toISOString(), bucket: "hour" };
  }
  const days = preset === "7d" ? 6 : 29;
  return {
    since: startOfLocalDay(now, -days).toISOString(),
    until: startOfLocalDay(now, 1).toISOString(),
    bucket: "day",
  };
}

/** Events filter range: open-ended on the recent side, so the newest events always show. */
export function eventsSince(preset: EventsPreset, now: Date = new Date()): string | undefined {
  if (preset === "all") return undefined;
  return startOfLocalDay(now, preset === "today" ? 0 : -6).toISOString();
}

/** Start of today, for the dashboard's "Today" tiles. */
export function todaySince(now: Date = new Date()): string {
  return startOfLocalDay(now).toISOString();
}
