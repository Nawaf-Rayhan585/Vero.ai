import { apiClient } from "./client";
import type { Member, MemberAddRequest, Role } from "./types";

export const membersApi = {
  list: () => apiClient.get<Member[]>("/members"),
  add: (body: MemberAddRequest) => apiClient.post<Member>("/members", body),
  updateRole: (userId: string, role: Role) => apiClient.patch<Member>(`/members/${userId}`, { role }),
  remove: (userId: string) => apiClient.delete<void>(`/members/${userId}`),
};
