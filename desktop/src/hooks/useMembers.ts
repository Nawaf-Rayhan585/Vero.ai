import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { membersApi } from "../api/members";
import type { MemberAddRequest, Role } from "../api/types";

export function useMembers() {
  return useQuery({
    queryKey: ["members"],
    queryFn: membersApi.list,
  });
}

export function useAddMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MemberAddRequest) => membersApi.add(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) => membersApi.updateRole(userId, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => membersApi.remove(userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
  });
}
