import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { jobsApi } from "../api/jobs";
import { DetectPage } from "./DetectPage";
import type { Job } from "../api/types";

vi.mock("../api/jobs");
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

const jobsMock = vi.mocked(jobsApi);

function baseJob(overrides: Partial<Job>): Job {
  return {
    id: "job-1",
    video_source: "C:/media/a.jpg",
    model_type: "yolo",
    confidence_threshold: 0.25,
    status: "pending",
    created_at: "2026-01-01T00:00:00Z",
    result: null,
    error: null,
    ...overrides,
  };
}

async function selectFileAndSubmit(open: { mockResolvedValue: (value: string) => unknown }) {
  const user = userEvent.setup();
  open.mockResolvedValue("C:/media/a.jpg");
  await user.click(screen.getByRole("button", { name: "Select Video/Image" }));
  await screen.findByText("C:/media/a.jpg");
  await user.click(screen.getByRole("button", { name: "Run Detection" }));
  return user;
}

describe("DetectPage", () => {
  beforeEach(async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    vi.mocked(open).mockReset();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("disables Run Detection until a file is selected, so no job can be created", () => {
    renderWithProviders(<DetectPage />);

    expect(screen.getByRole("button", { name: "Run Detection" })).toBeDisabled();
    expect(jobsMock.create).not.toHaveBeenCalled();
  });

  it("while the job is pending, disables the submit button and shows a spinner", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    jobsMock.create.mockResolvedValue({ id: "job-1" });
    jobsMock.get.mockResolvedValue(baseJob({ status: "pending" }));

    renderWithProviders(<DetectPage />);
    await selectFileAndSubmit(vi.mocked(open));

    expect(await screen.findByRole("button", { name: "Processing..." })).toBeDisabled();
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("shows detections once the job completes", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    jobsMock.create.mockResolvedValue({ id: "job-1" });
    jobsMock.get.mockResolvedValue(
      baseJob({
        status: "completed",
        result: { type: "image", detections: [{ label: "person", confidence: 0.9, box: [1, 2, 3, 4] }] },
      }),
    );

    renderWithProviders(<DetectPage />);
    await selectFileAndSubmit(vi.mocked(open));

    expect(await screen.findByText(/person — 90.0%/)).toBeInTheDocument();
  });

  it("shows the error message when the job fails", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    jobsMock.create.mockResolvedValue({ id: "job-1" });
    jobsMock.get.mockResolvedValue(baseJob({ status: "failed", error: "Could not open video: bad.mp4" }));

    renderWithProviders(<DetectPage />);
    await selectFileAndSubmit(vi.mocked(open));

    expect(await screen.findByText("Error: Could not open video: bad.mp4")).toBeInTheDocument();
  });

  it("shows a backend error when job creation fails", async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    jobsMock.create.mockRejectedValue(new Error("Could not reach backend"));

    renderWithProviders(<DetectPage />);
    await selectFileAndSubmit(vi.mocked(open));

    expect(await screen.findByText(/Could not reach backend/)).toBeInTheDocument();
  });
});
