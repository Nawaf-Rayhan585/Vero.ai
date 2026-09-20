import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { zonesApi } from "../api/zones";
import { ZoneEditor } from "./ZoneEditor";
import type { Zone } from "../api/types";

const listSpy = vi.spyOn(zonesApi, "list");
const createSpy = vi.spyOn(zonesApi, "create");
const removeSpy = vi.spyOn(zonesApi, "remove");

const FRAME_ALT = "Camera frame for zone placement";

function makeZone(overrides: Partial<Zone> = {}): Zone {
  return {
    id: "zone-1",
    camera_id: "cam-1",
    name: "Checkout",
    points: [
      { x: 0.2, y: 0.2 },
      { x: 0.8, y: 0.2 },
      { x: 0.8, y: 0.8 },
    ],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// The mocked rendered size is 200x100, so pixel (px, py) maps to (px/200, py/100).
function clickAt(img: HTMLElement, x: number, y: number) {
  fireEvent.click(img, { clientX: x, clientY: y });
}

describe("ZoneEditor", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["jpeg-bytes"]), { status: 200 })));
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    listSpy.mockResolvedValue([]);
    // jsdom lays out nothing by default; fix a rendered size so click coordinates map
    // to predictable normalized fractions.
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 200,
      height: 100,
      right: 200,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  it("renders the camera frame to draw on", async () => {
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    expect(await screen.findByAltText(FRAME_ALT)).toBeInTheDocument();
  });

  it("guides the user through the first points", async () => {
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    expect(screen.getByText(/Click 3 or more points/)).toBeInTheDocument();

    clickAt(img, 20, 20);
    expect(screen.getByText(/1 point\(s\) placed — keep clicking/)).toBeInTheDocument();

    clickAt(img, 100, 20);
    clickAt(img, 100, 80);
    expect(screen.getByText(/3 points placed — click more to refine/)).toBeInTheDocument();
  });

  it("Finish zone stays disabled until 3 points are placed", async () => {
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 20, 20);
    clickAt(img, 100, 20);
    expect(screen.getByRole("button", { name: "Finish zone" })).toBeDisabled();

    clickAt(img, 100, 80);
    expect(screen.getByRole("button", { name: "Finish zone" })).toBeEnabled();
  });

  it("clicking points converts pixel coordinates to normalized 0-1, and saves them in order", async () => {
    createSpy.mockResolvedValue(makeZone());
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 40, 30); // 0.2, 0.3
    clickAt(img, 160, 30); // 0.8, 0.3
    clickAt(img, 160, 70); // 0.8, 0.7
    clickAt(img, 40, 70); // 0.2, 0.7
    await user.click(screen.getByRole("button", { name: "Finish zone" }));
    await user.type(screen.getByLabelText("Name"), "Back aisle");
    await user.click(screen.getByRole("button", { name: "Save zone" }));

    expect(createSpy).toHaveBeenCalledWith("cam-1", {
      name: "Back aisle",
      points: [
        { x: 0.2, y: 0.3 },
        { x: 0.8, y: 0.3 },
        { x: 0.8, y: 0.7 },
        { x: 0.2, y: 0.7 },
      ],
    });
  });

  it("Undo last point removes only the most recent point", async () => {
    createSpy.mockResolvedValue(makeZone());
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 40, 30);
    clickAt(img, 160, 30);
    clickAt(img, 160, 70);
    clickAt(img, 40, 70);
    await user.click(screen.getByRole("button", { name: "Undo last point" }));
    await user.click(screen.getByRole("button", { name: "Finish zone" }));
    await user.type(screen.getByLabelText("Name"), "Triangle");
    await user.click(screen.getByRole("button", { name: "Save zone" }));

    expect(createSpy).toHaveBeenCalledWith("cam-1", {
      name: "Triangle",
      points: [
        { x: 0.2, y: 0.3 },
        { x: 0.8, y: 0.3 },
        { x: 0.8, y: 0.7 },
      ],
    });
  });

  it("undoing back below 3 points disables Finish zone again", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 20, 20);
    clickAt(img, 100, 20);
    clickAt(img, 100, 80);
    await user.click(screen.getByRole("button", { name: "Undo last point" }));

    expect(screen.getByRole("button", { name: "Finish zone" })).toBeDisabled();
  });

  it("clicks after Finish zone are ignored", async () => {
    createSpy.mockResolvedValue(makeZone());
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 40, 30);
    clickAt(img, 160, 30);
    clickAt(img, 160, 70);
    await user.click(screen.getByRole("button", { name: "Finish zone" }));
    clickAt(img, 40, 70); // too late — the outline is closed
    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save zone" }));

    expect(createSpy).toHaveBeenCalledWith("cam-1", expect.objectContaining({ points: expect.any(Array) }));
    expect(createSpy.mock.calls[0][1].points).toHaveLength(3);
  });

  it("Save zone is disabled without a name", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 20, 20);
    clickAt(img, 100, 20);
    clickAt(img, 100, 80);
    await user.click(screen.getByRole("button", { name: "Finish zone" }));

    expect(screen.getByRole("button", { name: "Save zone" })).toBeDisabled();
  });

  it("Cancel discards the in-progress zone without saving", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 20, 20);
    clickAt(img, 100, 20);
    clickAt(img, 100, 80);
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText(/Click 3 or more points/)).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("draws each existing zone as a polygon over the frame", async () => {
    listSpy.mockResolvedValue([makeZone()]);
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    await screen.findByAltText(FRAME_ALT);

    const polygon = await vi.waitFor(() => {
      const found = document.querySelector("polygon.line-editor__existing-zone");
      expect(found).not.toBeNull();
      return found as Element;
    });
    expect(polygon.getAttribute("points")).toBe("20,20 80,20 80,80");
  });

  it("lists existing zones and deletes one on request", async () => {
    listSpy.mockResolvedValue([makeZone()]);
    removeSpy.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);

    expect(await screen.findByText("Checkout")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(removeSpy).toHaveBeenCalledWith("zone-1");
  });

  it("shows an error if creating a zone fails", async () => {
    createSpy.mockRejectedValue(new Error("Server returned 500"));
    const user = userEvent.setup();
    renderWithProviders(<ZoneEditor cameraId="cam-1" />);
    const img = await screen.findByAltText(FRAME_ALT);

    clickAt(img, 20, 20);
    clickAt(img, 100, 20);
    clickAt(img, 100, 80);
    await user.click(screen.getByRole("button", { name: "Finish zone" }));
    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save zone" }));

    expect(await screen.findByText("Server returned 500")).toBeInTheDocument();
  });
});
