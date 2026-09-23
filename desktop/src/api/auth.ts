import { apiClient } from "./client";
import type { ChangePasswordRequest, LoginRequest, MeResponse, RegisterRequest, TokenPair } from "./types";

export const authApi = {
  register: (body: RegisterRequest) => apiClient.post<TokenPair>("/auth/register", body),
  login: (body: LoginRequest) => apiClient.post<TokenPair>("/auth/login", body),
  refresh: (refreshToken: string) => apiClient.post<TokenPair>("/auth/refresh", { refresh_token: refreshToken }),
  logout: (refreshToken: string) => apiClient.post<void>("/auth/logout", { refresh_token: refreshToken }),
  me: () => apiClient.get<MeResponse>("/auth/me"),
  changePassword: (body: ChangePasswordRequest) => apiClient.post<TokenPair>("/auth/change-password", body),
};
