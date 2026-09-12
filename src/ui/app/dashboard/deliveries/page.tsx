"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import LoadingShimmer from "@/components/LoadingShimmer";
import { cn } from "@/lib/utils";
import { Truck, CheckCircle, Clock, AlertCircle, Package } from "lucide-react";

const CARE_RECIPIENT_ID = "cr-001";

const STATUS_CONFIG: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string }> = {
  delivered: { icon: CheckCircle, color: "text-green-600 bg-green-50" },
  in_transit: { icon: Clock, color: "text-blue-600 bg-blue-50" },
  pending: { icon: Package, color: "text-amber-600 bg-amber-50" },
  failed: { icon: AlertCircle, color: "text-red-600 bg-red-50" },
};

export default function DeliveriesPage() {
  const { data: deliveries, isLoading } = useQuery({
    queryKey: ["deliveries", CARE_RECIPIENT_ID],
    queryFn: () => api.getDeliveries(CARE_RECIPIENT_ID),
  });

  if (isLoading) return <LoadingShimmer lines={5} />;

  if (!deliveries || deliveries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 py-12 text-center text-sm text-muted">
        No delivery history.
      </div>
    );
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-stone-900">Deliveries</h2>
      <div className="space-y-3">
        {deliveries.map((d) => {
          const cfg = STATUS_CONFIG[d.status] ?? STATUS_CONFIG["pending"]!;
          const Icon = cfg.icon;
          return (
            <div
              key={d.delivery_id}
              className="flex items-center gap-4 rounded-xl border border-stone-200 bg-white p-4"
            >
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", cfg.color)}>
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="flex-1">
                <p className="font-medium text-stone-900 capitalize">{d.status.replace("_", " ")}</p>
                {d.expected_at && (
                  <p className="text-xs text-muted">
                    Expected: {new Date(d.expected_at).toLocaleString()}
                  </p>
                )}
                {d.failure_reason && (
                  <p className="mt-1 text-xs text-red-600">Reason: {d.failure_reason}</p>
                )}
              </div>
              <Truck className="h-4 w-4 text-stone-400" aria-hidden="true" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
