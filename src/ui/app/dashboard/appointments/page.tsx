"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type AppointmentOut } from "@/lib/api";
import LoadingShimmer from "@/components/LoadingShimmer";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import ConfirmDialog from "@/components/ConfirmDialog";
import AppointmentModal from "@/components/AppointmentModal";
import { useToast } from "@/components/Toast";
import {
  CalendarDays,
  MapPin,
  Car,
  Plus,
  X,
} from "lucide-react";

export default function AppointmentsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AppointmentOut | null>(null);
  const [cancelling, setCancelling] = useState<AppointmentOut | null>(null);

  const { data: appointments, isLoading, isError } = useQuery({
    queryKey: ["crud-appointments"],
    queryFn: () => api.listAppointments(),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelAppointment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["crud-appointments"] });
      showToast("Appointment cancelled", "success");
      setCancelling(null);
    },
    onError: () => {
      showToast("Failed to cancel appointment", "error");
    },
  });

  const handleEdit = (appt: AppointmentOut) => {
    setEditing(appt);
    setModalOpen(true);
  };

  const handleAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["crud-appointments"] });
    showToast(editing ? "Appointment updated" : "Appointment added", "success");
  };

  if (isLoading) return <LoadingShimmer lines={5} />;
  if (isError) return <ErrorState message="Could not load appointments." onRetry={() => queryClient.invalidateQueries({ queryKey: ["crud-appointments"] })} />;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-serif text-xl text-forest">Appointments</h2>
        <button
          onClick={handleAdd}
          className="flex items-center gap-2 rounded-xl bg-forest px-4 py-2 text-sm font-medium text-cream shadow-sm transition-all hover:bg-forest-hover"
        >
          <Plus className="h-4 w-4" />
          Add appointment
        </button>
      </div>

      {/* List or empty */}
      {!appointments || appointments.length === 0 ? (
        <EmptyState
          title="No appointments"
          description="No upcoming appointments."
          action={
            <button
              onClick={handleAdd}
              className="flex items-center gap-2 rounded-xl bg-forest px-4 py-2 text-sm font-medium text-cream shadow-sm transition-all hover:bg-forest-hover"
            >
              <Plus className="h-4 w-4" />
              Schedule one
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {appointments.map((appt) => (
            <div
              key={appt.id}
              className="rounded-2xl border border-sand bg-white p-5"
            >
              <div className="flex items-start gap-4">
                {/* Date badge */}
                <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg bg-forest text-cream">
                  <span className="text-[10px] font-medium uppercase">
                    {new Date(appt.appointment_at).toLocaleDateString("en-US", { weekday: "short" }).toUpperCase()}
                  </span>
                  <span className="font-serif text-lg font-bold leading-none">
                    {new Date(appt.appointment_at).getDate()}
                  </span>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <CalendarDays className="h-4 w-4 text-forest" aria-hidden="true" />
                    <p className="font-medium text-charcoal">
                      {appt.specialty ?? appt.provider_name}
                    </p>
                    {/* Status badge */}
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      appt.status === "cancelled"
                        ? "bg-red-50 text-red-700"
                        : appt.status === "completed"
                          ? "bg-mint-light text-forest"
                          : "bg-sand-light text-charcoal"
                    }`}>
                      {appt.status}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-charcoal">{appt.provider_name}</p>
                  {appt.location && (
                    <div className="mt-1.5 flex items-center gap-1 text-xs text-muted">
                      <MapPin className="h-3 w-3" aria-hidden="true" />
                      {appt.location}
                    </div>
                  )}
                  <div className="mt-1 flex items-center gap-1 text-xs text-muted">
                    <CalendarDays className="h-3 w-3" aria-hidden="true" />
                    {new Date(appt.appointment_at).toLocaleTimeString("en-US", {
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </div>
                  {appt.transportation_needed && (
                    <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                      <Car className="h-3 w-3" aria-hidden="true" />
                      Transportation needed
                    </div>
                  )}
                  {appt.prep_required.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-charcoal">Prep:</p>
                      <ul className="mt-1 list-inside list-disc text-xs text-muted">
                        {appt.prep_required.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Actions */}
                  {appt.status !== "cancelled" && appt.status !== "completed" && (
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        onClick={() => handleEdit(appt)}
                        className="rounded-lg border border-sand px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-sand-light"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setCancelling(appt)}
                        className="flex items-center gap-1 rounded-lg border border-sand px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                      >
                        <X className="h-3 w-3" />
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <AppointmentModal
        open={modalOpen}
        appointment={editing}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSaved={handleSaved}
      />
      <ConfirmDialog
        open={!!cancelling}
        title="Cancel appointment"
        message={`Cancel your appointment with ${cancelling?.provider_name ?? "the provider"}? This action will be logged to the audit trail.`}
        confirmLabel="Cancel appointment"
        variant="danger"
        onConfirm={() => cancelling && cancelMutation.mutate(cancelling.id)}
        onCancel={() => setCancelling(null)}
      />
    </div>
  );
}
