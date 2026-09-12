"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import AlertFeed from "@/components/AlertFeed";

const CARE_RECIPIENT_ID = "cr-001";

export default function AlertsPage() {
  const queryClient = useQueryClient();

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", CARE_RECIPIENT_ID],
    queryFn: () => api.getAlerts(CARE_RECIPIENT_ID),
    refetchInterval: 5_000,
  });

  const ackMutation = useMutation({
    mutationFn: (id: string) => api.ackAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-stone-900">Alerts</h2>
      <AlertFeed
        events={alerts ?? []}
        onAck={(id) => ackMutation.mutate(id)}
        loading={isLoading}
      />
    </div>
  );
}
