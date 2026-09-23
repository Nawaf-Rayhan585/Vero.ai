import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { trackingApi } from "../api/tracking";
import { linesApi } from "../api/lines";
import { zonesApi } from "../api/zones";
import { AIModulesPage } from "./AIModulesPage";
import type { Camera, TrackingStatus } from "../api/types";

const listSpy = vi.spyOn(camerasApi, "list");
const statusSpy = vi.spyOn(trackingApi, "status");
const startSpy = vi.spyOn(trackingApi, "start");
const stopSpy = vi.spyOn(trackingApi, "stop");
const linesListSpy = vi.spyOn(linesApi, "list");
const zonesListSpy = vi.spyOn(zonesApi, "list");

function makeCamera(overrides: Partial<Camera> = {}): Camera {
  return {
    id: "cam-1",
    name: "Front door",
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
    line_counts: [],
    zone_counts: [],
    active_vehicle_track_ids: [],
    reads: [],
    ...overrides,
  };
}

describe("AIModulesPage", () => {
  beforeEach(() => {
    statusSpy.mockResolvedValue(makeStatus());
    linesListSpy.mockResolvedValue([]);
    zonesListSpy.mockResolvedValue([]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["jpeg-bytes"]), { status: 200 })));
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it("shows live in/out counts for each configured line", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    statusSpy.mockResolvedValue(
      makeStatus({
        status: "running",
        line_counts: [
          { line_id: "line-1", name: "Entrance", in_count: 3, out_count: 1, vehicle_in_count: 0, vehicle_out_count: 0 },
        ],
      }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Entrance: 3 in / 1 out")).toBeInTheDocument();
  });

  it("shows the live count of people inside each configured zone", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    statusSpy.mockResolvedValue(
      makeStatus({
        status: "running",
        zone_counts: [
          { zone_id: "zone-1", name: "Checkout", count: 2 },
          { zone_id: "zone-2", name: "Entrance mat", count: 0 },
        ],
      }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Checkout: 2 inside")).toBeInTheDocument();
    expect(screen.getByText("Entrance mat: 0 inside")).toBeInTheDocument();
  });

  it("clicking Zones opens the zone editor for that camera, and again closes it", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    const user = userEvent.setup();
    renderWithProviders(<AIModulesPage />);

    await user.click(await screen.findByRole("button", { name: "Zones" }));
    expect(await screen.findByAltText("Camera frame for zone placement")).toBeInTheDocument();
    expect(screen.queryByAltText("Camera frame for line placement")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide zones" }));
    expect(screen.queryByAltText("Camera frame for zone placement")).not.toBeInTheDocument();
  });

  it("shows a vehicle count next to the people count when Vehicles is on", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["people", "vehicles"] })]);
    statusSpy.mockResolvedValue(
      makeStatus({ status: "running", active_track_ids: [1, 2], active_vehicle_track_ids: [7] }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText(/2 person\(s\) tracked, 1 vehicle\(s\) tracked/)).toBeInTheDocument();
  });

  it("shows only vehicles when People is off", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["vehicles"] })]);
    statusSpy.mockResolvedValue(makeStatus({ status: "running", active_vehicle_track_ids: [7, 8, 9] }));
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText(/3 vehicle\(s\) tracked/)).toBeInTheDocument();
    expect(screen.queryByText(/person\(s\) tracked/)).not.toBeInTheDocument();
  });

  it("appends vehicle in/out to a line's people counts when Vehicles is on", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["people", "vehicles"] })]);
    statusSpy.mockResolvedValue(
      makeStatus({
        status: "running",
        line_counts: [
          { line_id: "line-1", name: "Gate", in_count: 3, out_count: 1, vehicle_in_count: 2, vehicle_out_count: 5 },
        ],
      }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Gate: 3 in / 1 out | vehicles 2 in / 5 out")).toBeInTheDocument();
  });

  it("shows only vehicle counts on a line for a vehicles-only camera", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["vehicles"] })]);
    statusSpy.mockResolvedValue(
      makeStatus({
        status: "running",
        line_counts: [
          { line_id: "line-1", name: "Gate", in_count: 0, out_count: 0, vehicle_in_count: 2, vehicle_out_count: 5 },
        ],
      }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Gate: vehicles 2 in / 5 out")).toBeInTheDocument();
  });

  it("lists recent reads: QR and barcodes with their symbology, text with its confidence", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["ocr", "qr", "barcode"] })]);
    statusSpy.mockResolvedValue(
      makeStatus({
        status: "running",
        reads: [
          { kind: "ocr", value: "PALLET 4471-B", detail: "0.99", first_seen_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-01-01T00:00:01Z", sightings: 1 },
          { kind: "barcode", value: "PKG-99812", detail: "Code 128", first_seen_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-01-01T00:00:01Z", sightings: 2 },
          { kind: "qr", value: "https://vero.ai/t/42", detail: "QR Code", first_seen_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-01-01T00:00:01Z", sightings: 3 },
        ],
      }),
    );
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText("Recent reads")).toBeInTheDocument();
    expect(screen.getByText("Text: PALLET 4471-B (99% confident) · seen 1×")).toBeInTheDocument();
    expect(screen.getByText("Barcode: PKG-99812 (Code 128) · seen 2×")).toBeInTheDocument();
    expect(screen.getByText("QR: https://vero.ai/t/42 (QR Code) · seen 3×")).toBeInTheDocument();
  });

  it("shows at most the 10 most recent reads", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["ocr"] })]);
    const reads = Array.from({ length: 15 }, (_, i) => ({
      kind: "ocr" as const,
      value: `line-${i}`,
      detail: "0.9",
      first_seen_at: "2026-01-01T00:00:00Z",
      last_seen_at: "2026-01-01T00:00:00Z",
      sightings: 1,
    }));
    statusSpy.mockResolvedValue(makeStatus({ status: "running", reads }));
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText(/line-0 \(/)).toBeInTheDocument();
    expect(screen.getByText(/line-9 \(/)).toBeInTheDocument();
    expect(screen.queryByText(/line-10 \(/)).not.toBeInTheDocument();
  });

  it("says it is watching, rather than showing an empty list, while a reading module has read nothing yet", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["qr", "barcode"] })]);
    statusSpy.mockResolvedValue(makeStatus({ status: "running" }));
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByText(/Watching for QR, Barcode; nothing read yet/)).toBeInTheDocument();
    expect(screen.queryByText("Recent reads")).not.toBeInTheDocument();
  });

  it("does not claim to be watching for reads on a camera with no reading module", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: ["people"] })]);
    statusSpy.mockResolvedValue(makeStatus({ status: "running" }));
    renderWithProviders(<AIModulesPage />);

    await screen.findByText("running");
    expect(screen.queryByText(/Watching for/)).not.toBeInTheDocument();
  });

  it("disables Start tracking, with a hint, when no module is ticked", async () => {
    listSpy.mockResolvedValue([makeCamera({ enabled_modules: [] })]);
    renderWithProviders(<AIModulesPage />);

    expect(await screen.findByRole("button", { name: "Start tracking" })).toBeDisabled();
    expect(screen.getByText(/Tick at least one AI module/)).toBeInTheDocument();
  });

  it("each camera row has its own module selector", async () => {
    listSpy.mockResolvedValue([
      makeCamera({ enabled_modules: ["people"] }),
      makeCamera({ id: "cam-2", name: "Car park", enabled_modules: ["vehicles"] }),
    ]);
    renderWithProviders(<AIModulesPage />);

    await screen.findByText("Car park");
    const peopleBoxes = screen.getAllByLabelText("People");
    expect(peopleBoxes).toHaveLength(2);
    expect(peopleBoxes[0]).toBeChecked();
    expect(peopleBoxes[1]).not.toBeChecked();
  });

  it("clicking Lines opens the line editor for that camera, and again closes it", async () => {
    listSpy.mockResolvedValue([makeCamera()]);
    const user = userEvent.setup();
    renderWithProviders(<AIModulesPage />);

    await user.click(await screen.findByRole("button", { name: "Lines" }));
    expect(await screen.findByAltText("Camera frame for line placement")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide lines" }));
    expect(screen.queryByAltText("Camera frame for line placement")).not.toBeInTheDocument();
  });
});
