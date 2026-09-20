import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { getApiBaseUrl, setApiBaseUrlOverride } from "../api/config";
import { healthApi } from "../api/health";
import { TopBar } from "../components/layout/TopBar";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api/health");
const healthMock = vi.mocked(healthApi);

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setApiBaseUrlOverride(null);
  });

  it("rejects an invalid backend URL and does not save it", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const input = screen.getByLabelText("Backend URL");
    await user.clear(input);
    await user.type(input, "not-a-url");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/Enter a valid http\(s\) URL/)).toBeInTheDocument();
    expect(getApiBaseUrl()).not.toBe("not-a-url");
  });

  it("saves a valid backend URL so it persists for subsequent reads", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const input = screen.getByLabelText("Backend URL");
    await user.clear(input);
    await user.type(input, "http://192.168.1.50:8000");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(getApiBaseUrl()).toBe("http://192.168.1.50:8000");
  });

  it("Reset to default clears the override", async () => {
    setApiBaseUrlOverride("http://old-value:9000");
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(screen.getByRole("button", { name: "Reset to default" }));

    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
    expect(screen.getByLabelText("Backend URL")).toHaveValue("http://127.0.0.1:8000");
  });

  it("Test connection reports success when the backend responds", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Connected successfully.")).toBeInTheDocument();
  });

  it("Test connection reports failure when the backend is unreachable", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText(/Could not reach that address|Failed to fetch/)).toBeInTheDocument();
  });

  it("Save immediately rechecks connectivity instead of waiting for the next poll", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <TopBar />
        <SettingsPage />
      </>,
    );
    await screen.findByText("Backend connected");

    healthMock.health.mockRejectedValue(new Error("down"));
    const input = screen.getByLabelText("Backend URL");
    await user.clear(input);
    await user.type(input, "http://127.0.0.1:9999");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Backend offline")).toBeInTheDocument();
  });

  it("persists the default model and confidence threshold across remounts", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<SettingsPage />);

    await user.selectOptions(screen.getByLabelText("Default model"), "yolo_seg");
    unmount();

    renderWithProviders(<SettingsPage />);
    expect(screen.getByLabelText("Default model")).toHaveValue("yolo_seg");
  });
});
