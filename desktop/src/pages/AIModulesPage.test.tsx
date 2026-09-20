import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { trackingApi } from "../api/tracking";
import { AIModulesPage } from "./AIModulesPage";
import type { Camera, TrackingStatus } from "../api/types";

const listSpy = vi.spyOn(camerasApi, "list");
const statusSpy = vi.spyOn(trackingApi, "status");
const startSpy = vi.spyOn(trackingApi, "start");
const stopSpy = vi.spyOn(trackingApi, "stop");

function makeCamera(overrides: Partial<Camera> = {}): Camera {
  return {
    id: "cam-1",
    name: "Front door",
    rtsp_url: "rtsp://192.0.2.10:554/stream1",
    username: null,
    has_password: false,
    location_label: null,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    connection_status: "unknown",
    last_tested_at: null,
    last_error: null,
    last_fps: null,
    last_width: null,
    last_height: null,
    ...overrides,
  };
}

function makeStatus(overrides: Partial<TrackingStatus> = {}): TrackingStatus {
  return {
    status: "stopped",
    error: null,
    frame_count: 0,
    started_at: null,
    last_frame_at: null,
    active_track_ids: [],
    ...overrides,
  };
}

describe("AIModulesPage", () => {
  beforeEach(() => {
    statusSpy.mockResolvedValue(makeStatus());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows an empty state when there are no cameras", async () => {
    listSpy.mockResolvedValue([]);
    renderWithProviders(<AIModulesPage />);
    expect(await screen.findByText("No cameras yet")).toBeInTheDocument();
  });

  it("shows a stopped camera with a Start tracking button", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Front door")).toBeInTheDocument();
    expect(await screen.findByText("stopped")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start tracking" })).toBeInTheDocument();
  });

  it("shows a running camera's track count and a Stop tracking button", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    statusSpy.mockResolvedValue(makeStatus({ status: "running", active_track_ids: [1, 2, 3] }));
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("running")).toBeInTheDocument();
    expect(screen.getByText(/3 person\(s\) tracked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop tracking" })).toBeInTheDocument();
  });

  it("shows the persisted error message when tracking has failed", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    statusSpy.mockResolvedValue(makeStatus({ status: "error", error: "Could not open stream" }));
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("error")).toBeInTheDocument();
    expect(screen.getByText("Could not open stream")).toBeInTheDocument();
  });

  it("clicking Start tracking calls the API with this camera's id", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    startSpy.mockResolvedValue(makeStatus({ status: "starting" }));
    const user = userEvent.setup();
    renderWithProviders(<AIModulesPage />);

    await user.click(await screen.findByRole("button", { name: "Start tracking" }));

    expect(startSpy).toHaveBeenCalledWith("cam-1");
  });

  it("clicking Stop tracking calls the API with this camera's id", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    statusSpy.mockResolvedValue(makeStatus({ status: "running" }));
    stopSpy.mockResolvedValue(makeStatus({ status: "stopped" }));
    const user = userEvent.setup();
    renderWithProviders(<AIModulesPage />);

    await user.click(await screen.findByRole("button", { name: "Stop tracking" }));

    expect(stopSpy).toHaveBeenCalledWith("cam-1");
  });

  it("shows a mutation error if starting tracking fails", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    startSpy.mockRejectedValue(new Error("Server returned 500"));
    const user = userEvent.setup();
    renderWithProviders(<AIModulesPage />);

    await user.click(await screen.findByRole("button", { name: "Start tracking" }));

    expect(await screen.findByText("Server returned 500")).toBeInTheDocument();
  });
});
