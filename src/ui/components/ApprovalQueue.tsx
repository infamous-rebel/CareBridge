"use client";

import React from "react";
import type { PendingAction } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Check, X, Clock } from "lucide-react";

interface ApprovalQueueProps {
  actions: PendingAction[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  loading?: boolean;
}

export default function ApprovalQueue({
  actions,
  onApprove,
  onReject,
  loading,
}: ApprovalQueueProps) {
  if (loading) {
    return (
      <div className="space-y-3" role="status" aria-label="Loading approvals">
        {[1, 2].map((i) => (
          <div key={i} className="animate-shimmer h-24 rounded-lg" />
        ))}
      </div>
    );
  }

  if (actions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 py-8 text-center text-sm text-muted">
        No pending approvals. You&apos;re all caught up.
      </div>
    );
  }

  return (
    <ul className="space-y-3" aria-label="Pending approvals">
      {actions.map((action) => (
        <li
          key={action.action_id}
          className={cn(
            "rounded-lg border p-4",
            action.status === "pending"
              ? "border-amber-200 bg-amber-50/50"
              : "border-stone-200 bg-white",
          )}
        >
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
              <Clock className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-stone-900">
                {action.action_type.replace(/_/g, " ")}
              </p>
              <p className="mt-0.5 text-xs text-muted">{action.rationale}</p>
              <time className="mt-1 block text-xs text-muted" dateTime={action.requested_at}>
                Requested {new Date(action.requested_at).toLocaleString()}
              </time>
            </div>
          </div>
          {action.status === "pending" && (
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => onApprove(action.action_id)}
                className="inline-flex items-center gap-1 rounded-lg bg-forest-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-forest-700"
              >
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                Approve
              </button>
              <button
                onClick={() => onReject(action.action_id)}
                className="inline-flex items-center gap-1 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-700 transition-colors hover:bg-stone-50"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
                Reject
              </button>
            </div>
          )}
          {action.status !== "pending" && (
            <span
              className={cn(
                "mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                action.status === "approved"
                  ? "bg-green-100 text-green-700"
                  : "bg-red-100 text-red-700",
              )}
            >
              {action.status}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
