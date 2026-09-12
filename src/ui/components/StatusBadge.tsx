"use client";

import React from "react";
import { cn } from "@/lib/utils";

type Status = "nominal" | "degraded" | "error";

interface StatusBadgeProps {
  status: Status;
  label?: string;
  className?: string;
}

const CONFIG: Record<Status, { dot: string; text: string; label: string }> = {
  nominal: { dot: "bg-green-500", text: "text-green-700", label: "All systems nominal" },
  degraded: {
    dot: "bg-amber-500",
    text: "text-amber-700",
    label: "AI reasoning degraded — using fallback routing",
  },
  error: { dot: "bg-red-500", text: "text-red-700", label: "Service unavailable" },
};

export default function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const cfg = CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        "bg-white/80 ring-1 ring-inset ring-black/5",
        cfg.text,
        className,
      )}
      role="status"
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} aria-hidden="true" />
      {label ?? cfg.label}
    </span>
  );
}
