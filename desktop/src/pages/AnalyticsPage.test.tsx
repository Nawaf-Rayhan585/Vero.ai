import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { analyticsApi } from "../api/analytics";
import { camerasApi } from "../api/cameras";
import { browserTimeZone } from "../lib/ranges";
import { AnalyticsPage } from "./AnalyticsPage";
import type { AnalyticsSummary, Camera, HeatmapInfo, Timeseries, TimeseriesPoint } from "../api/types";

const summarySpy = vi.spyOn(analyticsApi, "summary");
const timeseriesSpy = vi.spyOn(analyticsApi, "timeseries");
const heatmapInfoSpy = vi.spyOn(analyticsApi, "heatmapInfo");
const camerasSpy = vi.spyOn(camerasApi, "list");

function makeCamera(id: string, name: string): Camera {
  return {
    id,
    name,
    rtsp_url: "rtsp://192.0.2.10:554/stream1",
    username: null,
    has_password: false,
    location_id: "loc-1",
    location_name: "Main location",
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    connection_status: "unknown",
    last_tested_at: null,
    last_error: null,
    last_fps: null,
    last_width: null,
    last_height: null,
    enabled_modules: ["people"],
  };
}

function makeSummary(overrides: Partial<AnalyticsSummary> = {}): AnalyticsSummary {
  return {
    since: "2026-03-10T00:00:00Z",
    until: "2026-03-11T00:00:00Z",
    people_in: 12,
    people_out: 7,
    vehicle_in: 3,
    vehicle_out: 2,
    lines: [],
    zones: [],
    reads: { qr: 2, barcode: 1, ocr: 4 },
    tracked_seconds: 2 * 3600 + 15 * 60,
    ...overrides,
  };
}

function makePoint(hour: number, overrides: Partial<TimeseriesPoint> = {}): TimeseriesPoint {
  const pad = String(hour).padStart(2, "0");
  const next = String(hour + 1).padStart(2, "0");
  return {
    start: `2026-03-10T${pad}:00:00Z`,
    end: `2026-03-10T${next}:00:00Z`,
    people_in: 0,
    people_out: 0,
    vehicle_in: 0,
    vehicle_out: 0,
    zone_entered: 0,
    zone_exited: 0,
    reads: 0,
    tracked_seconds: 3600,
    ...overrides,
  };
}

function makeSeries(points: TimeseriesPoint[], bucket: "hour" | "day" = "hour"): Timeseries {
  return { bucket, tz: "UTC", since: "2026-03-10T00:00:00Z", until: "2026-03-11T00:00:00Z", points };
}

// Some tile labels ("Reads", "Zone visits") are also options in the Measure menu, so look
// specifically for the tile's own label.
function tile(label: string): HTMLElement {
  const labelElement = screen.getAllByText(label).find((el) => el.classList.contains("stat-tile__label"));
  return labelElement!.closest(".stat-tile") as HTMLElement;
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    camerasSpy.mockResolvedValue([makeCamera("cam-1", "Front door"), makeCamera("cam-2", "Car park")]);
    summarySpy.mockResolvedValue(makeSummary());
    timeseriesSpy.mockResolvedValue(
      makeSeries([makePoint(9, { people_in: 3, people_out: 1 }), makePoint(10, { tracked_seconds: 0 }), makePoint(11, { people_in: 12, people_out: 4 })]),
    );
    heatmapInfoSpy.mockResolvedValue({ camera_id: "cam-1", available: false, samples: 0 } as HeatmapInfo);
    URL.createObjectURL = vi.fn(() => "blob:heat");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  describe("the numbers", () => {
    it("shows the headline totals as tiles", async () => {
      renderWithProviders(<AnalyticsPage />);

      await screen.findByText("People in");
      expect(within(tile("People in")).getByText("12")).toBeInTheDocument();
      expect(within(tile("People out")).getByText("7")).toBeInTheDocument();
      expect(within(tile("Vehicles in")).getByText("3")).toBeInTheDocument();
      expect(within(tile("Vehicles out")).getByText("2")).toBeInTheDocument();
      expect(within(tile("Reads")).getByText("7")).toBeInTheDocument(); // 2 + 1 + 4
      expect(within(tile("Tracked")).getByText("2 h 15 min")).toBeInTheDocument();
    });

    it("counts zone visits as the sum of entries across zones", async () => {
      summarySpy.mockResolvedValue(
        makeSummary({
          zones: [
            { zone_id: "z1", name: "Checkout", entered: 5, exited: 4 },
            { zone_id: "z2", name: "Entrance mat", entered: 8, exited: 8 },
          ],
        }),
      );

      renderWithProviders(<AnalyticsPage />);

      await screen.findByRole("table", { name: "By zone" }); // only there once the summary has loaded
      expect(within(tile("Zone visits")).getByText("13")).toBeInTheDocument();
    });

    it("breaks the totals down by line and by zone when there are any", async () => {
      summarySpy.mockResolvedValue(
        makeSummary({
          lines: [{ line_id: "l1", name: "Entrance", people_in: 9, people_out: 6, vehicle_in: 1, vehicle_out: 0 }],
          zones: [{ zone_id: "z1", name: "Checkout", entered: 5, exited: 4 }],
        }),
      );

      renderWithProviders(<AnalyticsPage />);

      const byLine = await screen.findByRole("table", { name: "By line" });
      expect(within(byLine).getByRole("rowheader", { name: "Entrance" })).toBeInTheDocument();
      expect(within(byLine).getByText("9")).toBeInTheDocument();
      const byZone = screen.getByRole("table", { name: "By zone" });
      expect(within(byZone).getByRole("rowheader", { name: "Checkout" })).toBeInTheDocument();
    });

    it("names a line that has since been deleted rather than showing a blank", async () => {
      summarySpy.mockResolvedValue(
        makeSummary({ lines: [{ line_id: "gone", name: null, people_in: 1, people_out: 0, vehicle_in: 0, vehicle_out: 0 }] }),
      );

      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByRole("rowheader", { name: "(deleted line)" })).toBeInTheDocument();
    });

    it("says plainly when nothing was tracked, instead of presenting zeros as a finding", async () => {
      summarySpy.mockResolvedValue(makeSummary({ people_in: 0, people_out: 0, tracked_seconds: 0 }));

      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByText(/Nothing was tracked in this period/)).toBeInTheDocument();
    });

    it("does not say that when tracking did run", async () => {
      renderWithProviders(<AnalyticsPage />);

      await screen.findByText("People in");
      expect(screen.queryByText(/Nothing was tracked/)).not.toBeInTheDocument();
    });

    it("dims the totals while another camera's numbers load, rather than showing the last camera's as if they were current", async () => {
      const user = userEvent.setup();
      const { container } = renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");
      await waitFor(() => expect(container.querySelector(".stat-tiles--stale")).toBeNull());
      let release!: (summary: AnalyticsSummary) => void;
      summarySpy.mockImplementation(() => new Promise((resolve) => { release = resolve; }));

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-2");

      expect(container.querySelector(".stat-tiles--stale")).not.toBeNull();
      expect(within(tile("People in")).getByText("12")).toBeInTheDocument(); // still the old numbers, but visibly stale

      release(makeSummary({ people_in: 99 }));
      await waitFor(() => expect(container.querySelector(".stat-tiles--stale")).toBeNull());
      expect(within(tile("People in")).getByText("99")).toBeInTheDocument();
    });

    it("shows the real error if the summary cannot be loaded", async () => {
      summarySpy.mockRejectedValue(new Error("Could not reach backend"));

      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByText("Could not reach backend")).toBeInTheDocument();
    });
  });

  describe("what it asks the API for", () => {
    it("starts with today, in hourly buckets, in the browser's own time zone", async () => {
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      expect(timeseriesSpy).toHaveBeenCalledWith(
        expect.objectContaining({ bucket: "hour", tz: browserTimeZone(), camera_id: undefined }),
      );
      expect(summarySpy).toHaveBeenCalledWith(expect.objectContaining({ camera_id: undefined }));
      expect(screen.getByText(`Times shown in ${browserTimeZone()}`)).toBeInTheDocument();
    });

    it("today's range starts at local midnight", async () => {
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      const now = new Date();
      const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
      expect(summarySpy).toHaveBeenCalledWith(expect.objectContaining({ since: midnight }));
    });

    it.each([
      ["Last 7 days", 6],
      ["Last 30 days", 29],
    ])("%s switches to daily buckets covering that many days", async (label, daysBack) => {
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Period"), label);

      const now = new Date();
      const since = new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysBack).toISOString();
      expect(timeseriesSpy).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: "day", since }));
      expect(summarySpy).toHaveBeenLastCalledWith(expect.objectContaining({ since }));
    });

    it("choosing a camera scopes the totals and the trend to it", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-2");

      expect(summarySpy).toHaveBeenLastCalledWith(expect.objectContaining({ camera_id: "cam-2" }));
      expect(timeseriesSpy).toHaveBeenLastCalledWith(expect.objectContaining({ camera_id: "cam-2" }));
    });
  });

  describe("the chart", () => {
    it("charts people in and out per hour by default, with a legend", async () => {
      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByRole("group", { name: "People per hour" })).toBeInTheDocument();
      expect(screen.getByText("In")).toBeInTheDocument();
      expect(screen.getByText("Out")).toBeInTheDocument();
    });

    it("a daily range says per day", async () => {
      timeseriesSpy.mockResolvedValue(makeSeries([makePoint(0)], "day"));
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByRole("group", { name: "People per hour" });

      await user.selectOptions(screen.getByLabelText("Period"), "Last 7 days");

      expect(await screen.findByRole("group", { name: "People per day" })).toBeInTheDocument();
    });

    it("hatches an hour where nothing was tracked and labels it, rather than showing it as zero traffic", async () => {
      const { container } = renderWithProviders(<AnalyticsPage />);

      await screen.findByRole("group", { name: "People per hour" });
      expect(container.querySelectorAll('rect[fill^="url(#hatch"]')).toHaveLength(1);
      expect(screen.getByText("Not running")).toBeInTheDocument(); // the legend entry
      expect(screen.getAllByRole("img").some((el) => (el.getAttribute("aria-label") ?? "").includes("Not running"))).toBe(true);
    });

    it("switching the measure redraws with that measure's series", async () => {
      timeseriesSpy.mockResolvedValue(makeSeries([makePoint(9, { zone_entered: 4, zone_exited: 3 })]));
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByRole("group", { name: "People per hour" });

      await user.selectOptions(screen.getByLabelText("Measure"), "Zone visits");

      expect(await screen.findByRole("group", { name: "Zone visits per hour" })).toBeInTheDocument();
      expect(screen.getByText("Entered")).toBeInTheDocument();
      expect(screen.getByText("Left")).toBeInTheDocument();
    });

    it("reads are one series, so there is no legend box for them", async () => {
      timeseriesSpy.mockResolvedValue(makeSeries([makePoint(9, { reads: 5 })]));
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByRole("group", { name: "People per hour" });

      await user.selectOptions(screen.getByLabelText("Measure"), "Reads");

      await screen.findByRole("group", { name: "Reads per hour" });
      expect(document.querySelector(".chart__legend-item")).toBeNull();
    });

    it("keeps each direction's colour when the measure changes", async () => {
      timeseriesSpy.mockResolvedValue(makeSeries([makePoint(9, { people_in: 3, people_out: 2, vehicle_in: 5, vehicle_out: 1 })]));
      const user = userEvent.setup();
      const { container } = renderWithProviders(<AnalyticsPage />);
      await screen.findByRole("group", { name: "People per hour" });
      const colours = () => Array.from(container.querySelectorAll("svg path")).map((p) => (p.getAttribute("style") ?? "").match(/series-(\d)/)![1]);
      expect(colours()).toEqual(["1", "2"]);

      await user.selectOptions(screen.getByLabelText("Measure"), "Vehicles");

      await screen.findByRole("group", { name: "Vehicles per hour" });
      expect(colours()).toEqual(["1", "2"]); // in is still slot 1, out still slot 2
    });

    it("notes that several cameras' tracked time is summed when looking at all of them", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByRole("group", { name: "People per hour" });

      await user.click(screen.getByRole("button", { name: "Show table" }));

      expect(screen.getAllByText(/camera time, summed/).length).toBeGreaterThan(0);
    });

    it("shows the real error if the trend cannot be loaded", async () => {
      timeseriesSpy.mockRejectedValue(new Error("Unknown time zone: 'Mars/Olympus'"));

      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByText("Unknown time zone: 'Mars/Olympus'")).toBeInTheDocument();
    });
  });

  describe("the heatmap", () => {
    function stubHeatmapImage(headers: Record<string, string>, status = 200, body: BodyInit = new Blob(["jpeg"])) {
      const fetchMock = vi.fn(async (_url: RequestInfo | URL) => new Response(body, { status, headers }));
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    it("asks for a camera to be chosen when looking at all of them", async () => {
      renderWithProviders(<AnalyticsPage />);

      expect(await screen.findByText(/Choose a camera above to see where people stood/)).toBeInTheDocument();
      expect(heatmapInfoSpy).not.toHaveBeenCalled();
    });

    it("says so, and how to fix it, when no heat was recorded for that camera and period", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");

      expect(await screen.findByText("No heatmap recorded for this camera in this period")).toBeInTheDocument();
      expect(screen.getByText(/Heat is saved while people are being tracked/)).toBeInTheDocument();
    });

    it("draws the saved heatmap with its sample count, saying it sits on a live snapshot", async () => {
      heatmapInfoSpy.mockResolvedValue({
        camera_id: "cam-1", available: true, samples: 1234, frame_width: 800, frame_height: 400,
        grid_width: 80, grid_height: 40, first_period: "2026-03-10T09:00:00Z", last_period: "2026-03-10T11:00:00Z", ignored_samples: 0,
      });
      const fetchMock = stubHeatmapImage({ "X-Heatmap-Background": "snapshot", "X-Heatmap-Samples": "1234" });
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");

      const image = await screen.findByAltText("Heatmap of where people stood in this period");
      expect(image).toHaveAttribute("src", "blob:heat");
      expect(screen.getByText(/1,234 position samples/)).toBeInTheDocument();
      expect(screen.getByText(/over a current snapshot from the camera/)).toBeInTheDocument();
      const requested = new URL(String(fetchMock.mock.calls[0][0]));
      expect(requested.pathname).toBe("/analytics/heatmap");
      expect(requested.searchParams.get("camera_id")).toBe("cam-1");
    });

    it("says when the camera did not answer and the heat is on a plain background", async () => {
      heatmapInfoSpy.mockResolvedValue({
        camera_id: "cam-1", available: true, samples: 50, frame_width: 800, frame_height: 400,
        grid_width: 80, grid_height: 40, first_period: null, last_period: null, ignored_samples: 0,
      });
      stubHeatmapImage({ "X-Heatmap-Background": "neutral", "X-Heatmap-Samples": "50" });
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");

      expect(await screen.findByText(/did not answer, so the heat is drawn on a plain background/)).toBeInTheDocument();
    });

    it("mentions samples that were left out because the camera's resolution changed", async () => {
      heatmapInfoSpy.mockResolvedValue({
        camera_id: "cam-1", available: true, samples: 50, frame_width: 800, frame_height: 400,
        grid_width: 80, grid_height: 40, first_period: null, last_period: null, ignored_samples: 1500,
      });
      stubHeatmapImage({ "X-Heatmap-Background": "neutral" });
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");

      expect(await screen.findByText(/1,500 samples from a different camera resolution are not shown/)).toBeInTheDocument();
    });

    it("shows the server's message if the picture itself cannot be produced", async () => {
      heatmapInfoSpy.mockResolvedValue({
        camera_id: "cam-1", available: true, samples: 50, frame_width: 800, frame_height: 400,
        grid_width: 80, grid_height: 40, first_period: null, last_period: null, ignored_samples: 0,
      });
      stubHeatmapImage({ "Content-Type": "application/json" }, 404, JSON.stringify({ detail: "No heatmap was recorded for this camera in that period" }));
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");

      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");

      expect(await screen.findByText("No heatmap was recorded for this camera in that period")).toBeInTheDocument();
    });

    it("asks for the heatmap of the chosen period", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AnalyticsPage />);
      await screen.findByText("People in");
      await user.selectOptions(screen.getByLabelText("Camera"), "cam-1");
      await screen.findByText("No heatmap recorded for this camera in this period");

      await user.selectOptions(screen.getByLabelText("Period"), "Last 7 days");

      const now = new Date();
      const since = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6).toISOString();
      expect(heatmapInfoSpy).toHaveBeenLastCalledWith(expect.objectContaining({ camera_id: "cam-1", since }));
    });
  });
});
