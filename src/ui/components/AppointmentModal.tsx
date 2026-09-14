"use client";

import React, { useState, useEffect } from "react";
import { X } from "lucide-react";
import { api, type AppointmentOut } from "@/lib/api";

/** Convert a UTC ISO string to a local datetime-local input value. */
function toLocalDatetimeInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface AppointmentModalProps {
  open: boolean;
  appointment?: AppointmentOut | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function AppointmentModal({
  open,
  appointment,
  onClose,
  onSaved,
}: AppointmentModalProps) {
  const isEdit = !!appointment;
  const [form, setForm] = useState<{
    provider_name: string;
    specialty: string;
    appointment_at: string;
    location: string;
    prep_required: string[];
    transportation_needed: boolean;
    notes: string;
  }>({
    provider_name: "",
    specialty: "",
    appointment_at: "",
    location: "",
    prep_required: [],
    transportation_needed: false,
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (appointment) {
      setForm({
        provider_name: appointment.provider_name,
        specialty: appointment.specialty ?? "",
        appointment_at: toLocalDatetimeInput(appointment.appointment_at),
        location: appointment.location ?? "",
        prep_required: appointment.prep_required ?? [],
        transportation_needed: appointment.transportation_needed,
        notes: appointment.notes ?? "",
      });
    } else {
      setForm({
        provider_name: "",
        specialty: "",
        appointment_at: "",
        location: "",
        prep_required: [],
        transportation_needed: false,
        notes: "",
      });
    }
    setError("");
  }, [appointment, open]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const payload = {
        ...form,
        appointment_at: new Date(form.appointment_at).toISOString(),
        specialty: form.specialty || undefined,
        location: form.location || undefined,
        notes: form.notes || undefined,
      };
      if (isEdit && appointment) {
        await api.updateAppointment(appointment.id, payload);
      } else {
        await api.createAppointment(payload);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save appointment";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-charcoal/40 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? "Edit appointment" : "Add appointment"}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-sand bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-sand px-6 py-4">
          <h3 className="font-serif text-lg text-forest">
            {isEdit ? "Edit Appointment" : "Add Appointment"}
          </h3>
          <button onClick={onClose} className="text-muted hover:text-forest" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-charcoal">Provider name *</label>
            <input
              type="text"
              required
              value={form.provider_name}
              onChange={(e) => setForm({ ...form, provider_name: e.target.value })}
              className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              placeholder="e.g. Dr. Vance"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-charcoal">Specialty</label>
              <input
                type="text"
                value={form.specialty}
                onChange={(e) => setForm({ ...form, specialty: e.target.value })}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
                placeholder="e.g. Cardiology"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-charcoal">Date & time *</label>
              <input
                type="datetime-local"
                required
                value={form.appointment_at}
                onChange={(e) =>
                  setForm({ ...form, appointment_at: e.target.value })
                }
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal">Location</label>
            <input
              type="text"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              placeholder="e.g. Mercy General Hospital"
            />
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.transportation_needed}
              onChange={(e) => setForm({ ...form, transportation_needed: e.target.checked })}
              className="h-4 w-4 rounded border-sand text-forest focus:ring-forest"
            />
            <span className="text-sm text-charcoal">Transportation needed</span>
          </label>

          <div>
            <label className="block text-sm font-medium text-charcoal">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              placeholder="Optional notes"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-sand px-4 py-2 text-sm font-medium text-charcoal hover:bg-sand-light"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-forest px-5 py-2 text-sm font-medium text-white hover:bg-forest-hover disabled:opacity-50"
            >
              {saving ? "Saving…" : isEdit ? "Update" : "Add Appointment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
