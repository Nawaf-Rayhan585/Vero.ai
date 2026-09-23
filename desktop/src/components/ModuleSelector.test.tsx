import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { ModuleSelector } from "./ModuleSelector";
import type { AIModule, Camera } from "../api/types";

const updateSpy = vi.spyOn(camerasApi, "update");

function makeCamera(enabled_modules: AIModule[] = ["people"]): Camera {
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
    enabled_modules,
  };
}

describe("ModuleSelector", () => {
  beforeEach(() => {
    updateSpy.mockResolvedValue(makeCamera());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("offers all five modules and ticks the camera's current selection", () => {
    renderWithProviders(<ModuleSelector camera={makeCamera(["people", "qr"])} isRunning={false} />);

    for (const label of ["People", "Vehicles", "Text (OCR)", "QR codes", "Barcodes"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("People")).toBeChecked();
    expect(screen.getByLabelText("QR codes")).toBeChecked();
    expect(screen.getByLabelText("Vehicles")).not.toBeChecked();
    expect(screen.getByLabelText("Text (OCR)")).not.toBeChecked();
    expect(screen.getByLabelText("Barcodes")).not.toBeChecked();
  });

  it("ticking a module saves the new selection to the camera", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["people"])} isRunning={false} />);

    await user.click(screen.getByLabelText("Vehicles"));

    expect(updateSpy).toHaveBeenCalledWith("cam-1", { enabled_modules: ["people", "vehicles"] });
  });

  it("unticking a module removes just that one", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["people", "vehicles", "barcode"])} isRunning={false} />);

    await user.click(screen.getByLabelText("Vehicles"));

    expect(updateSpy).toHaveBeenCalledWith("cam-1", { enabled_modules: ["people", "barcode"] });
  });

  it("always saves in the canonical module order, whatever order they were ticked in", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["barcode"])} isRunning={false} />);

    await user.click(screen.getByLabelText("People"));

    expect(updateSpy).toHaveBeenCalledWith("cam-1", { enabled_modules: ["people", "barcode"] });
  });

  it("allows unticking everything (starting is what's blocked, not saving)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["people"])} isRunning={false} />);

    await user.click(screen.getByLabelText("People"));

    expect(updateSpy).toHaveBeenCalledWith("cam-1", { enabled_modules: [] });
  });

  it("a click is reflected immediately, in the same tick, not after the save has started", () => {
    // Regression, found by the live browser check: showing the click via the mutation's
    // pending state only updates a tick later, and a controlled checkbox snaps back to its
    // old value in between — so the box didn't visibly change at the moment of the click.
    updateSpy.mockImplementation(() => new Promise(() => {}));
    renderWithProviders(<ModuleSelector camera={makeCamera(["people"])} isRunning={false} />);

    fireEvent.click(screen.getByLabelText("Vehicles"));
    expect(screen.getByLabelText("Vehicles")).toBeChecked(); // no await: must already be true

    fireEvent.click(screen.getByLabelText("People"));
    expect(screen.getByLabelText("People")).not.toBeChecked();
  });

  it("goes back to the saved selection if the save fails", async () => {
    updateSpy.mockRejectedValue(new Error("Server returned 500"));
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["people"])} isRunning={false} />);

    await user.click(screen.getByLabelText("Vehicles"));

    await screen.findByText("Server returned 500");
    expect(screen.getByLabelText("Vehicles")).not.toBeChecked();
    expect(screen.getByLabelText("People")).toBeChecked();
  });

  it("two quick clicks build on each other instead of both starting from the stale selection", async () => {
    // The first save never resolves, like a slow request; the UI must show the click and
    // let the second one build on it.
    updateSpy.mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera(["people"])} isRunning={false} />);

    await user.click(screen.getByLabelText("Vehicles"));
    expect(screen.getByLabelText("Vehicles")).toBeChecked();
    await user.click(screen.getByLabelText("QR codes"));

    expect(updateSpy).toHaveBeenLastCalledWith("cam-1", { enabled_modules: ["people", "vehicles", "qr"] });
  });

  it("tells the user changes apply on the next start, but only while tracking is running", () => {
    const { unmount } = renderWithProviders(<ModuleSelector camera={makeCamera()} isRunning={false} />);
    expect(screen.queryByText(/apply the next time tracking starts/)).not.toBeInTheDocument();
    unmount();

    renderWithProviders(<ModuleSelector camera={makeCamera()} isRunning={true} />);
    expect(screen.getByText(/apply the next time tracking starts/)).toBeInTheDocument();
  });

  it("shows the error if saving fails", async () => {
    updateSpy.mockRejectedValue(new Error("Server returned 500"));
    const user = userEvent.setup();
    renderWithProviders(<ModuleSelector camera={makeCamera()} isRunning={false} />);

    await user.click(screen.getByLabelText("Barcodes"));

    expect(await screen.findByText("Server returned 500")).toBeInTheDocument();
  });
});
