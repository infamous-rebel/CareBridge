"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import ApprovalQueue from "@/components/ApprovalQueue";

export default function ApprovalsPage() {
  const queryClient = useQueryClient();

  const { data: approvals, isLoading } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.getApprovals(),
    refetchInterval: 10_000,
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => api.approveAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.rejectAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-stone-900">Approval Queue</h2>
      <ApprovalQueue
        actions={approvals ?? []}
        onApprove={(id) => approveMutation.mutate(id)}
        onReject={(id) => rejectMutation.mutate(id)}
        loading={isLoading}
      />
    </div>
  );
}
