import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/renderWithProviders";
import { healthApi } from "../../api/health";
import { TopBar } from "./TopBar";

vi.mock("../../api/health");

const healthMock = vi.mocked(healthApi);

describe("TopBar", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows connected once the health check succeeds", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    renderWithProviders(<TopBar />);
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
  });

  it("shows offline once a health check fails, even though earlier data was 'ok'", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    const { queryClient } = renderWithProviders(<TopBar />);
    await screen.findByText("Backend connected");

    healthMock.health.mockRejectedValue(new Error("down"));
    await queryClient.refetchQueries({ queryKey: ["health"] });

    expect(await screen.findByText("Backend offline")).toBeInTheDocument();
  });
});
