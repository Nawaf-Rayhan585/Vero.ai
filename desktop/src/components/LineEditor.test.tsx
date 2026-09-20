import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { linesApi } from "../api/lines";
import { LineEditor } from "./LineEditor";
import type { Line } from "../api/types";

const listSpy = vi.spyOn(linesApi, "list");
const createSpy = vi.spyOn(linesApi, "create");
const removeSpy = vi.spyOn(linesApi, "remove");

function makeLine(overrides: Partial<Line> = {}): Line {
  return {
    id: "line-1",
    camera_id: "cam-1",
    name: "Entrance",
    x1: 0.1,
    y1: 0.2,
    x2: 0.9,
    y2: 0.8,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("LineEditor", () => {
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
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    expect(await screen.findByAltText("Camera frame for line placement")).toBeInTheDocument();
  });

  it("prompts for a second point after the first click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    expect(screen.getByText(/Click two points/)).toBeInTheDocument();
    await user.click(img);
    expect(screen.getByText(/Click one more point/)).toBeInTheDocument();
  });

  it("clicking two points converts pixel coordinates to normalized 0-1 and saves", async () => {
    createSpy.mockResolvedValue(makeLine());
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    fireEvent.click(img, { clientX: 40, clientY: 30 }); // 40/200=0.2, 30/100=0.3
    fireEvent.click(img, { clientX: 160, clientY: 70 }); // 160/200=0.8, 70/100=0.7

    await user.type(screen.getByLabelText("Name"), "Back door");
    await user.click(screen.getByRole("button", { name: "Save line" }));

    expect(createSpy).toHaveBeenCalledWith("cam-1", { name: "Back door", x1: 0.2, y1: 0.3, x2: 0.8, y2: 0.7 });
  });

  it("a third click is ignored once two points are already placed", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    fireEvent.click(img, { clientX: 10, clientY: 10 });
    fireEvent.click(img, { clientX: 20, clientY: 20 });
    fireEvent.click(img, { clientX: 30, clientY: 30 });

    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save line" }));

    expect(createSpy).toHaveBeenCalledWith("cam-1", expect.objectContaining({ x1: 0.05, y1: 0.1, x2: 0.1, y2: 0.2 }));
  });

  it("Cancel discards the in-progress line without saving", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    fireEvent.click(img, { clientX: 10, clientY: 10 });
    fireEvent.click(img, { clientX: 20, clientY: 20 });
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText(/Click two points/)).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("shows a validation-style guard: Save is disabled without a name", async () => {
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    fireEvent.click(img, { clientX: 10, clientY: 10 });
    fireEvent.click(img, { clientX: 20, clientY: 20 });

    expect(screen.getByRole("button", { name: "Save line" })).toBeDisabled();
  });

  it("lists existing lines and deletes one on request", async () => {
    listSpy.mockResolvedValue([makeLine()]);
    removeSpy.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(removeSpy).toHaveBeenCalledWith("line-1");
  });

  it("shows an error if creating a line fails", async () => {
    createSpy.mockRejectedValue(new Error("Server returned 500"));
    const user = userEvent.setup();
    renderWithProviders(<LineEditor cameraId="cam-1" />);
    const img = await screen.findByAltText("Camera frame for line placement");

    fireEvent.click(img, { clientX: 10, clientY: 10 });
    fireEvent.click(img, { clientX: 20, clientY: 20 });
    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save line" }));

    expect(await screen.findByText("Server returned 500")).toBeInTheDocument();
  });
});
