import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { eventsApi } from "../api/events";
import { EventsPage } from "./EventsPage";
import type { AppEvent, Camera } from "../api/types";

const listSpy = vi.spyOn(eventsApi, "list");
const camerasSpy = vi.spyOn(camerasApi, "list");

function makeCamera(id: string, name: string): Camera {
  return {
    id,
    name,
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
    enabled_modules: ["people"],
  };
}

let counter = 0;
function makeEvent(overrides: Partial<AppEvent> = {}): AppEvent {
  counter += 1;
  return {
    id: `event-${counter}`,
    camera_id: "cam-1",
    camera_name: "Front door",
    occurred_at: "2026-03-10T12:00:00Z",
    event_type: "line_crossed",
    category: "person",
    direction: "in",
    subject_id: "line-1",
    subject_name: "Entrance",
    value: null,
    detail: null,
    ...overrides,
  };
}

describe("EventsPage", () => {
  beforeEach(() => {
    counter = 0;
    camerasSpy.mockResolvedValue([makeCamera("cam-1", "Front door"), makeCamera("cam-2", "Car park")]);
    listSpy.mockResolvedValue({ events: [], next_before: null });
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("explains what will appear here when there are no events yet", async () => {
    renderWithProviders(<EventsPage />);

    expect(await screen.findByText("No events yet")).toBeInTheDocument();
    expect(screen.getByText(/Start tracking on a camera under AI Modules/)).toBeInTheDocument();
  });

  it("lists events newest first, each as a sentence with its camera and what it concerned", async () => {
    listSpy.mockResolvedValue({
      events: [
        makeEvent({ event_type: "read", category: "qr", value: "https://vero.ai/t/42", detail: "QR Code", subject_name: null }),
        makeEvent({ category: "vehicle", direction: "out", subject_name: "Gate", camera_name: "Car park" }),
        makeEvent({ event_type: "zone_entered", category: "person", direction: null, subject_name: "Checkout" }),
      ],
      next_before: null,
    });

    renderWithProviders(<EventsPage />);

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("QR code read")).toBeInTheDocument();
    expect(within(rows[0]).getByText("https://vero.ai/t/42 (QR Code)")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Vehicle crossed out")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Car park")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Line: Gate")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Person entered zone")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Checkout")).toBeInTheDocument();
  });

  it("shows problems and recoveries in tones that match, so an outage stands out", async () => {
    listSpy.mockResolvedValue({
      events: [
        makeEvent({ event_type: "tracking_error", category: null, direction: null, subject_name: null, value: "Could not open stream" }),
        makeEvent({ event_type: "tracking_reconnecting", category: null, direction: null, subject_name: null }),
        makeEvent({ event_type: "tracking_started", category: null, direction: null, subject_name: null }),
      ],
      next_before: null,
    });

    renderWithProviders(<EventsPage />);

    expect((await screen.findByText("Tracking error")).className).toContain("danger");
    expect(screen.getByText("Connection lost, reconnecting").className).toContain("warning");
    expect(screen.getByText("Tracking started").className).toContain("success");
    expect(screen.getByText("Could not open stream")).toBeInTheDocument();
  });

  it("asks for the first page of everything to start with", async () => {
    renderWithProviders(<EventsPage />);
    await screen.findByText("No events yet");

    expect(listSpy).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 50, before: null, camera_id: undefined, event_type: undefined, since: undefined }),
    );
  });

  it("filtering by camera asks the API for just that camera", async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);
    await screen.findByText("No events yet");

    await user.selectOptions(screen.getByLabelText("Camera"), "cam-2");

    expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ camera_id: "cam-2" }));
  });

  it("filtering by type sends every event type in that group", async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);
    await screen.findByText("No events yet");

    await user.selectOptions(screen.getByLabelText("Type"), "Zone activity");

    expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ event_type: ["zone_entered", "zone_exited"] }));

    await user.selectOptions(screen.getByLabelText("Type"), "All events");
    expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ event_type: undefined }));
  });

  it("the period filter starts at local midnight for Today", async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);
    await screen.findByText("No events yet");

    await user.selectOptions(screen.getByLabelText("Period"), "Today");

    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
    expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ since: midnight }));
  });

  it("offers Load more only while there is an older page, and appends it", async () => {
    listSpy.mockImplementation(async (query) => {
      if (query?.before === "cursor-1") {
        return { events: [makeEvent({ subject_name: "Older line" })], next_before: null };
      }
      return { events: [makeEvent({ subject_name: "Newest line" })], next_before: "cursor-1" };
    });
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    await screen.findByText("Line: Newest line");
    await user.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("Line: Older line")).toBeInTheDocument();
    expect(screen.getByText("Line: Newest line")).toBeInTheDocument(); // still there
    expect(listSpy).toHaveBeenCalledWith(expect.objectContaining({ before: "cursor-1" }));
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("does not show Load more when everything fits on one page", async () => {
    listSpy.mockResolvedValue({ events: [makeEvent()], next_before: null });

    renderWithProviders(<EventsPage />);

    await screen.findByText("Line: Entrance");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows the real error when events cannot be loaded, not an empty list", async () => {
    listSpy.mockRejectedValue(new Error("Could not reach backend"));

    renderWithProviders(<EventsPage />);

    expect(await screen.findByText("Could not reach backend")).toBeInTheDocument();
    expect(screen.queryByText("No events yet")).not.toBeInTheDocument();
  });

  it("says it updates on its own", async () => {
    renderWithProviders(<EventsPage />);

    expect(await screen.findByText(/updates automatically/)).toBeInTheDocument();
  });
});
