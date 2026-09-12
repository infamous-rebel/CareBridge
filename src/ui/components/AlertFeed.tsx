"use client";

import React from "react";
import type { AuditEvent } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  AlertCircle,
  Info,
} from "lucide-react";

interface AlertFeedProps {
  events: AuditEvent[];
  onAck?: (id: string) => void;
  loading?: boolean;
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  send_alert: AlertTriangle,
  send_sms: AlertCircle,
  send_email: Info,
  order_refill: CheckCircle,
  schedule_appointment: Clock,
  check_refill_status: Info,
};

const OUTCOME_STYLES: Record<string, string> = {
  success: "bg-green-50 text-green-700",
  failure: "bg-red-50 text-red-700",
  pending: "bg-amber-50 text-amber-700",
  escalated: "bg-orange-50 text-orange-700",
};

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function AlertFeed({ events, onAck, loading }: AlertFeedProps) {
  if (loading) {
    return (
      <div className="space-y-3" role="status" aria-label="Loading alerts">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-shimmer h-16 rounded-lg" />
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 py-8 text-center text-sm text-muted">
        No recent alerts. Everything looks calm.
      </div>
    );
  }

  return (
    <ul className="space-y-3" aria-label="Alert feed">
      {events.map((event) => {
        const Icon = ICON_MAP[event.action_type] ?? Info;
        return (
          <li
            key={event.event_id}
            className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg",
                  OUTCOME_STYLES[event.outcome] ?? "bg-stone-100 text-stone-600",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-stone-900">
                    {event.action_type.replace(/_/g, " ")}
                  </p>
                  <time className="flex-shrink-0 text-xs text-muted" dateTime={event.timestamp}>
                    {timeAgo(event.timestamp)}
                  </time>
                </div>
                <p className="mt-0.5 text-xs text-muted">{event.rationale}</p>
                {onAck && event.outcome !== "success" && (
                  <button
                    onClick={() => onAck(event.event_id)}
                    className="mt-2 text-xs font-medium text-forest-600 hover:text-forest-700"
                  >
                    Acknowledge
                  </button>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
