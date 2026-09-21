import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/renderWithProviders";
import { healthApi } from "../api/health";
import { analyticsApi } from "../api/analytics";
import { jobsApi } from "../api/jobs";
import { DashboardPage } from "./DashboardPage";
import type { AnalyticsSummary, Job } from "../api/types";

vi.mock("../api/health");
vi.mock("../api/jobs");
vi.mock("../api/analytics");

const healthMock = vi.mocked(healthApi);
const jobsMock = vi.mocked(jobsApi);
const analyticsMock = vi.mocked(analyticsApi);

function makeSummary(overrides: Partial<AnalyticsSummary> = {}): AnalyticsSummary {
  return {
    since: "2026-03-10T00:00:00Z",
    until: "2026-03-10T15:00:00Z",
    people_in: 42,
    people_out: 40,
    vehicle_in: 5,
    vehicle_out: 4,
    lines: [],
    zones: [],
    reads: { qr: 1, barcode: 2, ocr: 3 },
    tracked_seconds: 5400,
    ...overrides,
  };
}

function makeJob(overrides: Partial<Job>): Job {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    video_source: "a.jpg",
    model_type: "yolo",
    confidence_threshold: 0.25,
    status: "completed",
    created_at: "2026-01-01T00:00:00Z",
    result: { type: "image", detections: [] },
    error: null,
    ...overrides,
  };
}

describe("DashboardPage", () => {
  beforeEach(() => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    healthMock.healthDb.mockResolvedValue({ status: "ok" });
    jobsMock.list.mockResolvedValue([]);
    analyticsMock.summary.mockResolvedValue(makeSummary());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows the offline card and the configured backend URL when the backend is unreachable", async () => {
    healthMock.health.mockRejectedValue(new Error("Could not reach backend"));

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText("Backend offline")).toBeInTheDocument();
    expect(screen.getByText("http://127.0.0.1:8000")).toBeInTheDocument();
  });

  it("shows online status for both backend and database, and an empty state with no jobs", async () => {
    renderWithProviders(<DashboardPage />);

    expect(await screen.findAllByText("Online")).toHaveLength(2);
    expect(screen.getByText("No detection jobs yet")).toBeInTheDocument();
  });

  it("lists recent jobs, most recent first, linking to the detect page", async () => {
    jobsMock.list.mockResolvedValue([
      makeJob({ id: "aaaaaaaa-0000-0000-0000-000000000000", video_source: "first.jpg", status: "completed" }),
      makeJob({ id: "bbbbbbbb-0000-0000-0000-000000000000", video_source: "second.jpg", status: "failed" }),
    ]);

    renderWithProviders(<DashboardPage />);

    const secondLink = await screen.findByRole("link", { name: "second.jpg" });
    const firstLink = screen.getByRole("link", { name: "first.jpg" });
    expect(secondLink).toHaveAttribute("href", expect.stringContaining("bbbbbbbb"));

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toContainElement(secondLink);
    expect(items[1]).toContainElement(firstLink);
  });

  it("shows the backend as offline once a health check fails, even though earlier data was 'ok'", async () => {
    const { queryClient } = renderWithProviders(<DashboardPage />);
    await screen.findAllByText("Online");

    healthMock.health.mockRejectedValue(new Error("Could not reach backend"));
    await queryClient.refetchQueries({ queryKey: ["health"] });

    expect(await screen.findByText("Backend offline")).toBeInTheDocument();
  });

  it("shows the database as unavailable when /health/db fails even though the backend is up", async () => {
    healthMock.healthDb.mockRejectedValue(new Error("db down"));

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
  });

  it("refetches jobs when Refresh is clicked", async () => {
    renderWithProviders(<DashboardPage />);
    await screen.findAllByText("Online");

    const initialCalls = jobsMock.list.mock.calls.length;
    screen.getByRole("button", { name: /refresh/i }).click();

    await waitFor(() => expect(jobsMock.list.mock.calls.length).toBeGreaterThan(initialCalls));
  });

  it("shows today's totals, and links to the full analytics", async () => {
    renderWithProviders(<DashboardPage />);

    await screen.findByText("Today");
    const tileValue = (label: string) => screen.getByText(label).closest(".stat-tile")?.textContent ?? "";
    expect(tileValue("People in")).toContain("42");
    expect(tileValue("People out")).toContain("40");
    expect(tileValue("Vehicles in")).toContain("5");
    expect(tileValue("Reads")).toContain("6");
    expect(tileValue("Tracked")).toContain("1 h 30 min");
    expect(screen.getByRole("link", { name: "See analytics" })).toHaveAttribute("href", "/analytics");
  });

  it("asks only for today, from local midnight", async () => {
    renderWithProviders(<DashboardPage />);
    await screen.findByText("Today");

    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
    expect(analyticsMock.summary).toHaveBeenCalledWith({ since: midnight });
  });

  it("leaves the Today card out, rather than showing an error of its own, if the summary cannot be loaded", async () => {
    analyticsMock.summary.mockRejectedValue(new Error("boom"));

    renderWithProviders(<DashboardPage />);

    expect(await screen.findAllByText("Online")).toHaveLength(2); // the dashboard itself is fine
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });
});
