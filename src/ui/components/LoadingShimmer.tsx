"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface LoadingShimmerProps {
  className?: string;
  lines?: number;
}

export default function LoadingShimmer({ className, lines = 3 }: LoadingShimmerProps) {
  return (
    <div className={cn("space-y-3", className)} role="status" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="animate-shimmer h-4 rounded"
          style={{ width: i === lines - 1 ? "60%" : "100%" }}
        />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
