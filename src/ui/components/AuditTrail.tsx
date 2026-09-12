"use client";

import React from "react";
import type { PaginatedAudit } from "@/lib/api";
import { cn } from "@/lib/utils";

interface AuditTrailProps {
  data: PaginatedAudit | undefined;
  page: number;
  onPageChange: (page: number) => void;
  loading?: boolean;
}

const ACTOR_COLORS: Record<string, string> = {
  supervisor: "bg-purple-100 text-purple-700",
  medication: "bg-blue-100 text-blue-700",
  appointment: "bg-cyan-100 text-cyan-700",
  logistics: "bg-orange-100 text-orange-700",
  communication: "bg-pink-100 text-pink-700",
  human: "bg-green-100 text-green-700",
};

const OUTCOME_STYLES: Record<string, string> = {
  success: "text-green-700",
  failure: "text-red-700",
  pending: "text-amber-700",
  escalated: "text-orange-700",
};

export default function AuditTrail({ data, page, onPageChange, loading }: AuditTrailProps) {
  if (loading || !data) {
    return (
      <div className="space-y-3" role="status" aria-label="Loading audit trail">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="animate-shimmer h-12 rounded-lg" />
        ))}
      </div>
    );
  }

  if (data.items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 py-8 text-center text-sm text-muted">
        No audit events found for the selected filters.
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="table">
          <thead>
            <tr className="border-b border-stone-200 text-left text-xs font-medium uppercase tracking-wider text-muted">
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Action</th>
              <th className="hidden px-4 py-3 md:table-cell">Rationale</th>
              <th className="px-4 py-3">Outcome</th>
              <th className="px-4 py-3">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {data.items.map((event) => (
              <tr key={event.event_id} className="transition-colors hover:bg-stone-50/50">
                <td className="px-4 py-3">
                  <span
                    className={cn(
                      "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                      ACTOR_COLORS[event.actor] ?? "bg-stone-100 text-stone-600",
                    )}
                  >
                    {event.actor}
                  </span>
                </td>
                <td className="px-4 py-3 font-medium text-stone-900">
                  {event.action_type.replace(/_/g, " ")}
                </td>
                <td className="hidden max-w-xs truncate px-4 py-3 text-muted md:table-cell">
                  {event.rationale}
                </td>
                <td className="px-4 py-3">
                  <span className={cn("text-xs font-medium", OUTCOME_STYLES[event.outcome] ?? "text-stone-600")}>
                    {event.outcome}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-muted">
                  {new Date(event.timestamp).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.pages > 1 && (
        <nav className="mt-4 flex items-center justify-center gap-2" aria-label="Audit pagination">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-muted">
            Page {page} of {data.pages}
          </span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= data.pages}
            className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 disabled:opacity-40"
          >
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
