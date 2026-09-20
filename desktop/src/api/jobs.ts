import { apiClient } from "./client";
import type { CreateJobRequest, Job } from "./types";

export const jobsApi = {
  create: (body: CreateJobRequest) => apiClient.post<{ id: string }>("/jobs", body),
  get: (id: string) => apiClient.get<Job>(`/jobs/${id}`),
  list: () => apiClient.get<Job[]>("/jobs"),
};
