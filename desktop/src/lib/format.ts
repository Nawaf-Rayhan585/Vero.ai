export function formatNumber(value: number): string {
  return value.toLocaleString();
}

/** "2 h 15 min", "45 min", "30 s", "0 min" — for how long tracking actually ran. */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.round(totalSeconds);
  if (seconds <= 0) return "0 min";
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

export function formatBucketLabel(iso: string, bucket: "hour" | "day", tz: string): string {
  const options: Intl.DateTimeFormatOptions =
    bucket === "hour" ? { timeZone: tz, hour: "numeric" } : { timeZone: tz, month: "short", day: "numeric" };
  return new Intl.DateTimeFormat(undefined, options).format(new Date(iso));
}

export function formatBucketFull(iso: string, bucket: "hour" | "day", tz: string): string {
  const options: Intl.DateTimeFormatOptions =
    bucket === "hour"
      ? { timeZone: tz, weekday: "short", month: "short", day: "numeric", hour: "numeric" }
      : { timeZone: tz, weekday: "short", month: "short", day: "numeric" };
  return new Intl.DateTimeFormat(undefined, options).format(new Date(iso));
}

/** "10:42:07" for today's events, "Mar 10, 10:42:07" for older ones. */
export function formatEventTime(iso: string, now: Date = new Date()): string {
  const moment = new Date(iso);
  const time = moment.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
  if (moment.toDateString() === now.toDateString()) return time;
  return `${moment.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${time}`;
}
