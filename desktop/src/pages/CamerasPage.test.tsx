import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { camerasApi } from "../api/cameras";
import { CamerasPage } from "./CamerasPage";
import type { Camera } from "../api/types";

vi.mock("../api/cameras");
const camerasMock = vi.mocked(camerasApi);

function makeCamera(overrides: Partial<Camera> = {}): Camera {
  return {
    id: "11111111-1111-1111-1111-111111111111",
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

describe("CamerasPage", () => {
  beforeEach(() => {
    camerasMock.list.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows an empty state when there are no cameras", async () => {
    renderWithProviders(<CamerasPage />);
    expect(await screen.findByText("No cameras yet")).toBeInTheDocument();
  });

  it("lists cameras with a status badge", async () => {
    camerasMock.list.mockResolvedValue([makeCamera({ connection_status: "online" })]);
    renderWithProviders(<CamerasPage />);

    expect(await screen.findByText("Front door")).toBeInTheDocument();
    expect(screen.getByText("online")).toBeInTheDocument();
    expect(screen.getByText("rtsp://192.0.2.10:554/stream1")).toBeInTheDocument();
  });

  it("adding a camera submits the form and closes it on success", async () => {
    camerasMock.create.mockResolvedValue(makeCamera());
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Add camera" }));
    await user.type(screen.getByLabelText("Name"), "Front door");
    await user.type(screen.getByLabelText("RTSP URL"), "rtsp://192.0.2.10:554/stream1");
    await user.click(screen.getByRole("button", { name: "Add camera" }));

    expect(camerasMock.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Front door", rtsp_url: "rtsp://192.0.2.10:554/stream1" }),
    );
    expect(await screen.findByRole("button", { name: "Add camera" })).toBeInTheDocument();
  });

  it("shows a validation-free required-field guard: the browser blocks submit with an empty name", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Add camera" }));
    const nameInput = screen.getByLabelText("Name") as HTMLInputElement;
    expect(nameInput).toBeRequired();
  });

  it("editing a camera pre-fills the form and submits an update", async () => {
    camerasMock.list.mockResolvedValue([makeCamera({ location_label: "Warehouse" })]);
    camerasMock.update.mockResolvedValue(makeCamera({ name: "Back door" }));
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const nameInput = screen.getByLabelText("Name") as HTMLInputElement;
    expect(nameInput.value).toBe("Front door");
    expect((screen.getByLabelText("Location") as HTMLInputElement).value).toBe("Warehouse");

    await user.clear(nameInput);
    await user.type(nameInput, "Back door");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(camerasMock.update).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      expect.objectContaining({ name: "Back door" }),
    );
  });

  it("deletes a camera after confirmation", async () => {
    camerasMock.list.mockResolvedValue([makeCamera()]);
    camerasMock.remove.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(camerasMock.remove).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111");
  });

  it("does not delete when the confirmation is declined", async () => {
    camerasMock.list.mockResolvedValue([makeCamera()]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(camerasMock.remove).not.toHaveBeenCalled();
  });

  it("test connection shows the returned status, resolution, and fps", async () => {
    camerasMock.list.mockResolvedValue([makeCamera()]);
    camerasMock.testConnection.mockResolvedValue(
      makeCamera({
        connection_status: "online",
        last_tested_at: "2026-01-01T00:00:05Z",
        last_width: 1920,
        last_height: 1080,
        last_fps: 25,
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Test connection" }));

    expect(await screen.findByText(/1920×1080/)).toBeInTheDocument();
    expect(screen.getByText(/25\.0 fps/)).toBeInTheDocument();
  });

  it("test connection failure shows the persisted error", async () => {
    camerasMock.list.mockResolvedValue([makeCamera()]);
    camerasMock.testConnection.mockResolvedValue(
      makeCamera({ connection_status: "offline", last_error: "Could not open stream" }),
    );
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Could not open stream")).toBeInTheDocument();
  });

  it("shows a row-level error if deleting fails", async () => {
    camerasMock.list.mockResolvedValue([makeCamera()]);
    camerasMock.remove.mockRejectedValue(new Error("Server returned 500"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderWithProviders(<CamerasPage />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Server returned 500")).toBeInTheDocument();
  });
});
