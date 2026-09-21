import { describe, expect, it } from "vitest";
import { describeEvent, EVENT_FILTER_GROUPS } from "./describeEvent";
import { formatBucketFull, formatBucketLabel, formatDuration, formatEventTime, formatNumber } from "./format";
import { analyticsRange, browserTimeZone, eventsSince, startOfLocalDay, todaySince } from "./ranges";
import type { AppEvent, EventType } from "../api/types";

function makeEvent(overrides: Partial<AppEvent>): AppEvent {
  return {
    id: "e1",
    camera_id: "c1",
    camera_name: "Front door",
    occurred_at: "2026-03-10T12:00:00Z",
    event_type: "line_crossed",
    category: null,
    direction: null,
    subject_id: null,
    subject_name: null,
    value: null,
    detail: null,
    ...overrides,
  };
}

describe("ranges", () => {
  // A local time in the middle of a day, so the tests read the same in any time zone.
  const now = new Date(2026, 2, 10, 14, 35, 12);

  it("today runs from local midnight to the end of the current local hour, in hourly buckets", () => {
    expect(analyticsRange("today", now)).toEqual({
      since: new Date(2026, 2, 10).toISOString(),
      until: new Date(2026, 2, 10, 15).toISOString(),
      bucket: "hour",
    });
  });

  it("the end of the range is stable within the hour, so the query is not re-keyed on every render", () => {
    const early = analyticsRange("today", new Date(2026, 2, 10, 14, 1, 0));
    const late = analyticsRange("today", new Date(2026, 2, 10, 14, 59, 59));

    expect(early).toEqual(late);
  });

  it("7 days is the last seven local days including today, in daily buckets", () => {
    expect(analyticsRange("7d", now)).toEqual({
      since: new Date(2026, 2, 4).toISOString(),
      until: new Date(2026, 2, 11).toISOString(),
      bucket: "day",
    });
  });

  it("30 days is the last thirty local days including today", () => {
    expect(analyticsRange("30d", now)).toEqual({
      since: new Date(2026, 1, 9).toISOString(),
      until: new Date(2026, 2, 11).toISOString(),
      bucket: "day",
    });
  });

  it("counts back across a month boundary", () => {
    expect(analyticsRange("7d", new Date(2026, 2, 2, 9)).since).toBe(new Date(2026, 1, 24).toISOString());
  });

  it("events: all time has no lower bound, and the other presets start at local midnight", () => {
    expect(eventsSince("all", now)).toBeUndefined();
    expect(eventsSince("today", now)).toBe(new Date(2026, 2, 10).toISOString());
    expect(eventsSince("7d", now)).toBe(new Date(2026, 2, 4).toISOString());
  });

  it("todaySince is local midnight, and is the same string all day", () => {
    expect(todaySince(new Date(2026, 2, 10, 0, 0, 1))).toBe(todaySince(new Date(2026, 2, 10, 23, 59, 59)));
    expect(todaySince(now)).toBe(new Date(2026, 2, 10).toISOString());
  });

  it("startOfLocalDay can look backwards and forwards", () => {
    expect(startOfLocalDay(now, -1)).toEqual(new Date(2026, 2, 9));
    expect(startOfLocalDay(now, 1)).toEqual(new Date(2026, 2, 11));
  });

  it("knows the browser's time zone", () => {
    expect(browserTimeZone()).toMatch(/\w/);
  });
});

describe("format", () => {
  it("formats durations the way a person would say them", () => {
    expect(formatDuration(0)).toBe("0 min");
    expect(formatDuration(-5)).toBe("0 min");
    expect(formatDuration(30)).toBe("30 s");
    expect(formatDuration(59.6)).toBe("1 min");
    expect(formatDuration(45 * 60)).toBe("45 min");
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe("2 h 15 min");
    expect(formatDuration(26 * 3600)).toBe("26 h");
  });

  it("formats numbers with separators", () => {
    expect(formatNumber(1234567)).toBe((1234567).toLocaleString());
    expect(formatNumber(0)).toBe("0");
  });

  it("labels buckets in the requested time zone, not the machine's", () => {
    // 23:30 UTC is already the next day in Dhaka (UTC+6).
    expect(formatBucketLabel("2026-03-10T23:30:00Z", "day", "Asia/Dhaka")).toContain("11");
    expect(formatBucketLabel("2026-03-10T23:30:00Z", "day", "UTC")).toContain("10");
    expect(formatBucketFull("2026-03-10T23:30:00Z", "day", "Asia/Dhaka")).toContain("Mar");
  });

  it("hour labels show the hour", () => {
    expect(formatBucketLabel("2026-03-10T14:00:00Z", "hour", "UTC")).toMatch(/2|14/);
  });

  it("shows just the time for today's events and the date for older ones", () => {
    const now = new Date(2026, 2, 10, 15, 0, 0);
    const today = new Date(2026, 2, 10, 9, 5, 7).toISOString();
    const older = new Date(2026, 2, 8, 9, 5, 7).toISOString();

    expect(formatEventTime(today, now)).not.toMatch(/Mar/);
    expect(formatEventTime(older, now)).toMatch(/Mar/);
  });
});

describe("describeEvent", () => {
  it("line crossings say who and which way, and name the line", () => {
    expect(describeEvent(makeEvent({ category: "person", direction: "in", subject_name: "Entrance" }))).toEqual({
      title: "Person crossed in",
      detail: "Line: Entrance",
      tone: "neutral",
    });
    expect(describeEvent(makeEvent({ category: "vehicle", direction: "out", subject_name: "Gate" })).title).toBe(
      "Vehicle crossed out",
    );
  });

  it("zone events name the zone", () => {
    expect(describeEvent(makeEvent({ event_type: "zone_entered", category: "person", subject_name: "Checkout" }))).toEqual({
      title: "Person entered zone",
      detail: "Checkout",
      tone: "neutral",
    });
    expect(describeEvent(makeEvent({ event_type: "zone_exited", category: "person", subject_name: "Checkout" })).title).toBe(
      "Person left zone",
    );
  });

  it("reads say what kind, and show the value (with the symbology for codes)", () => {
    expect(describeEvent(makeEvent({ event_type: "read", category: "qr", value: "https://x", detail: "QR Code" }))).toEqual({
      title: "QR code read",
      detail: "https://x (QR Code)",
      tone: "neutral",
    });
    expect(describeEvent(makeEvent({ event_type: "read", category: "barcode", value: "PKG-1", detail: "Code 128" })).title).toBe(
      "Barcode read",
    );
    // For text, `detail` is a confidence score: not something to print after the words.
    expect(describeEvent(makeEvent({ event_type: "read", category: "ocr", value: "PALLET 4471-B", detail: "0.99" }))).toEqual({
      title: "Text read",
      detail: "PALLET 4471-B",
      tone: "neutral",
    });
  });

  it("uptime events carry a tone that matches how good or bad they are", () => {
    expect(describeEvent(makeEvent({ event_type: "tracking_started" })).tone).toBe("success");
    expect(describeEvent(makeEvent({ event_type: "tracking_resumed" })).tone).toBe("success");
    expect(describeEvent(makeEvent({ event_type: "tracking_reconnecting" })).tone).toBe("warning");
    expect(describeEvent(makeEvent({ event_type: "tracking_error", value: "Could not open stream" }))).toEqual({
      title: "Tracking error",
      detail: "Could not open stream",
      tone: "danger",
    });
    expect(describeEvent(makeEvent({ event_type: "tracking_stopped", value: "Backend restarted" })).detail).toBe(
      "Backend restarted",
    );
  });

  it("every event type has a description", () => {
    const all: EventType[] = [
      "line_crossed", "zone_entered", "zone_exited", "read", "tracking_started", "tracking_stopped",
      "tracking_error", "tracking_reconnecting", "tracking_resumed",
    ];
    for (const type of all) {
      expect(describeEvent(makeEvent({ event_type: type })).title).toBeTruthy();
    }
  });

  it("the filter groups cover every event type exactly once (apart from 'all')", () => {
    const covered = EVENT_FILTER_GROUPS.flatMap((g) => g.types);

    expect(new Set(covered).size).toBe(covered.length);
    expect(covered).toHaveLength(9);
    expect(EVENT_FILTER_GROUPS[0].types).toEqual([]);
  });
});
