import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { eventsApi, toQueryString } from "./events";
import { analyticsApi } from "./analytics";

describe("toQueryString", () => {
  it("leaves out anything empty, so the URL only says what was asked", () => {
    expect(toQueryString({ a: "x", b: undefined, c: null, d: "", e: 0 })).toBe("?a=x&e=0");
  });

  it("is empty when nothing is set", () => {
    expect(toQueryString({})).toBe("");
    expect(toQueryString({ a: undefined })).toBe("");
  });

  it("repeats a parameter for each array item", () => {
    expect(toQueryString({ event_type: ["zone_entered", "zone_exited"] })).toBe(
      "?event_type=zone_entered&event_type=zone_exited",
    );
  });

  it("encodes values, including the plus sign of a UTC offset and a cursor's pipe", () => {
    expect(toQueryString({ since: "2026-03-10T18:00:00+06:00" })).toBe("?since=2026-03-10T18%3A00%3A00%2B06%3A00");
    expect(toQueryString({ before: "2026-03-10T12:00:00Z|abc" })).toContain("%7C");
  });
});

describe("events and analytics API", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ events: [], next_before: null }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  function requestedUrl(): URL {
    return new URL(fetchMock.mock.calls[0][0] as string);
  }

  it("lists events with the filters as query parameters", async () => {
    await eventsApi.list({
      camera_id: "cam-1",
      event_type: ["read", "line_crossed"],
      since: "2026-03-10T00:00:00Z",
      limit: 50,
      before: "cursor",
    });

    const url = requestedUrl();
    expect(url.pathname).toBe("/events");
    expect(url.searchParams.get("camera_id")).toBe("cam-1");
    expect(url.searchParams.getAll("event_type")).toEqual(["read", "line_crossed"]);
    expect(url.searchParams.get("since")).toBe("2026-03-10T00:00:00Z");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("before")).toBe("cursor");
  });

  it("lists events with no filters as a bare /events", async () => {
    await eventsApi.list();

    expect(requestedUrl().search).toBe("");
  });

  it("requests the summary, the time series (with bucket and time zone) and the heatmap info", async () => {
    fetchMock.mockImplementation(async () => new Response("{}", { status: 200 }));

    await analyticsApi.summary({ since: "2026-03-10T00:00:00Z", camera_id: "cam-1" });
    await analyticsApi.timeseries({ since: "2026-03-10T00:00:00Z", until: "2026-03-11T00:00:00Z", bucket: "hour", tz: "Asia/Dhaka" });
    await analyticsApi.heatmapInfo({ camera_id: "cam-1", since: "2026-03-10T00:00:00Z" });

    const urls = fetchMock.mock.calls.map((call) => new URL(call[0] as string));
    expect(urls[0].pathname).toBe("/analytics/summary");
    expect(urls[0].searchParams.get("camera_id")).toBe("cam-1");
    expect(urls[1].pathname).toBe("/analytics/timeseries");
    expect(urls[1].searchParams.get("bucket")).toBe("hour");
    expect(urls[1].searchParams.get("tz")).toBe("Asia/Dhaka");
    expect(urls[1].searchParams.get("until")).toBe("2026-03-11T00:00:00Z");
    expect(urls[2].pathname).toBe("/analytics/heatmap/info");
  });

  it("builds the heatmap image URL without fetching it", () => {
    const url = new URL(analyticsApi.heatmapUrl({ camera_id: "cam-1", since: "2026-03-10T00:00:00Z", until: "2026-03-11T00:00:00Z" }));

    expect(url.pathname).toBe("/analytics/heatmap");
    expect(url.searchParams.get("camera_id")).toBe("cam-1");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
