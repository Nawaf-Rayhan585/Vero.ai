import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { trackingApi } from "../api/tracking";
import { LiveViewPage } from "./LiveViewPage";
import type { Camera, TrackingStatus } from "../api/types";

// `list`/`status` are faked via spyOn (not vi.mock) — `snapshotUrl`/`latestFrameUrl` must
// stay real so the blob-fetching hooks below hit the real (test-injected) URLs.
const listSpy = vi.spyOn(camerasApi, "list");
const trackingStatusSpy = vi.spyOn(trackingApi, "status");

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

function makeTrackingStatus(overrides: Partial<TrackingStatus> = {}): TrackingStatus {
  return {
    status: "stopped",
    error: null,
    frame_count: 0,
    started_at: null,
    last_frame_at: null,
    active_track_ids: [],
    line_counts: [],
    zone_counts: [],
    ...overrides,
  };
}

describe("LiveViewPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    // jsdom doesn't implement the Blob URL registry.
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    // Default: tracking not running, so existing snapshot-only tests below are
    // unaffected by LiveViewPage now also polling tracking status.
    trackingStatusSpy.mockResolvedValue(makeTrackingStatus());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  it("shows an empty state when there are no cameras", async () => {
    listSpy.mockResolvedValue([]);
    renderWithProviders(<LiveViewPage />);
    expect(await screen.findByText("No cameras yet")).toBeInTheDocument();
  });

  it("auto-selects the first camera and renders its snapshot as an object URL", async () => {
    listSpy.mockResolvedValue([makeCamera(), makeCamera({ id: "cam-2", name: "Back door" })]);
    vi.mocked(fetch).mockResolvedValue(new Response(new Blob(["jpeg-bytes"]), { status: 200 }));

    renderWithProviders(<LiveViewPage />);

    const img = await screen.findByRole("img", { name: "Live snapshot from Front door" });
    expect(img).toHaveAttribute("src", "blob:mock-url");
    expect(fetch).toHaveBeenCalledWith(camerasApi.snapshotUrl("cam-1"));
    expect(screen.getByRole("combobox")).toHaveValue("cam-1");
  });

  it("switching the camera picker fetches the newly selected camera's snapshot", async () => {
    listSpy.mockResolvedValue([makeCamera(), makeCamera({ id: "cam-2", name: "Back door" })]);
    // A Response body can only be read once, so each call needs its own fresh instance —
    // mockResolvedValue would hand back the same already-consumed Response every time.
    vi.mocked(fetch).mockImplementation(async () => new Response(new Blob(["jpeg-bytes"]), { status: 200 }));
    const user = userEvent.setup();
    renderWithProviders(<LiveViewPage />);
    await screen.findByRole("img", { name: "Live snapshot from Front door" });

    await user.selectOptions(screen.getByRole("combobox"), "cam-2");

    await screen.findByRole("img", { name: "Live snapshot from Back door" });
    expect(fetch).toHaveBeenCalledWith(camerasApi.snapshotUrl("cam-2"));
  });

  it("shows the real backend error instead of a broken image when the camera is unreachable", async () => {
    // Regression case: a plain <img src=snapshotUrl> never fires onError for this exact
    // response shape in real Chromium — Opaque Response Blocking silently drops a
    // non-image error body on a no-cors image request. Confirmed live against a real
    // unreachable camera before switching to this fetch-based approach.
    listSpy.mockResolvedValue([makeCamera()]);
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Could not open stream (unreachable, refused, or unsupported)" }), {
        status: 503,
      }),
    );

    renderWithProviders(<LiveViewPage />);

    expect(
      await screen.findByText(/Could not get a snapshot from "Front door"/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the error state (not a stale frame) once a previously-working camera starts failing", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(new Blob(["jpeg-bytes"]), { status: 200 }));
    const { queryClient } = renderWithProviders(<LiveViewPage />);
    await screen.findByRole("img", { name: "Live snapshot from Front door" });

    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "offline now" }), { status: 503 }));
    await queryClient.refetchQueries({ queryKey: ["image-blob", camerasApi.snapshotUrl("cam-1")] });

    expect(await screen.findByText(/Could not get a snapshot/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the AI-annotated tracking frame instead of the raw snapshot while tracking is running", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    trackingStatusSpy.mockResolvedValue(makeTrackingStatus({ status: "running", frame_count: 12, active_track_ids: [1, 2] }));
    vi.mocked(fetch).mockImplementation(async () => new Response(new Blob(["annotated-jpeg"]), { status: 200 }));

    renderWithProviders(<LiveViewPage />);

    const img = await screen.findByRole("img", { name: "Live snapshot from Front door" });
    expect(fetch).toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1"));
    expect(fetch).not.toHaveBeenCalledWith(camerasApi.snapshotUrl("cam-1"));
    expect(img).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("offers a Show heatmap toggle only while tracking is active", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    vi.mocked(fetch).mockImplementation(async () => new Response(new Blob(["jpeg-bytes"]), { status: 200 }));

    // Tracking stopped: raw snapshot, no toggle.
    const stopped = renderWithProviders(<LiveViewPage />);
    await screen.findByRole("img", { name: "Live snapshot from Front door" });
    expect(screen.queryByLabelText(/Show heatmap/)).not.toBeInTheDocument();
    stopped.unmount();

    // Tracking running: toggle appears.
    trackingStatusSpy.mockResolvedValue(makeTrackingStatus({ status: "running" }));
    renderWithProviders(<LiveViewPage />);
    expect(await screen.findByLabelText(/Show heatmap/)).not.toBeChecked();
  });

  it("ticking Show heatmap switches to the heat-overlay frame, and unticking switches back", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    trackingStatusSpy.mockResolvedValue(makeTrackingStatus({ status: "running", frame_count: 12 }));
    vi.mocked(fetch).mockImplementation(async () => new Response(new Blob(["annotated-jpeg"]), { status: 200 }));
    const user = userEvent.setup();
    renderWithProviders(<LiveViewPage />);
    await screen.findByRole("img", { name: "Live snapshot from Front door" });
    expect(fetch).toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1"));
    expect(fetch).not.toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1", { heatmap: true }));

    await user.click(screen.getByLabelText(/Show heatmap/));

    await vi.waitFor(() => expect(fetch).toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1", { heatmap: true })));
    expect(trackingApi.latestFrameUrl("cam-1", { heatmap: true })).toMatch(/\/tracking\/latest-frame\?heatmap=true$/);

    vi.mocked(fetch).mockClear();
    await user.click(screen.getByLabelText(/Show heatmap/));

    await vi.waitFor(() => expect(fetch).toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1")));
  });

  it("falls back to the raw snapshot once tracking stops", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    trackingStatusSpy.mockResolvedValue(makeTrackingStatus({ status: "stopped" }));
    vi.mocked(fetch).mockImplementation(async () => new Response(new Blob(["jpeg-bytes"]), { status: 200 }));

    renderWithProviders(<LiveViewPage />);

    await screen.findByRole("img", { name: "Live snapshot from Front door" });
    expect(fetch).toHaveBeenCalledWith(camerasApi.snapshotUrl("cam-1"));
    expect(fetch).not.toHaveBeenCalledWith(trackingApi.latestFrameUrl("cam-1"));
    expect(screen.queryByText("running")).not.toBeInTheDocument();
  });
});
