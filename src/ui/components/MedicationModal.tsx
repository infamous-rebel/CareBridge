"use client";

import React, { useState, useEffect } from "react";
import { X } from "lucide-react";
import { api, type MedicationOut } from "@/lib/api";

interface MedicationModalProps {
  open: boolean;
  medication?: MedicationOut | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function MedicationModal({
  open,
  medication,
  onClose,
  onSaved,
}: MedicationModalProps) {
  const isEdit = !!medication;
  const [form, setForm] = useState<{
    name: string;
    dosage: string;
    frequency: string;
    refill_threshold: number;
    pharmacy_id: string;
    notes: string;
  }>({
    name: "",
    dosage: "",
    frequency: "",
    refill_threshold: 5,
    pharmacy_id: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (medication) {
      setForm({
        name: medication.name,
        dosage: medication.dosage,
        frequency: medication.frequency,
        refill_threshold: medication.refill_threshold,
        pharmacy_id: medication.pharmacy_id ?? "",
        notes: medication.notes ?? "",
      });
    } else {
      setForm({
        name: "",
        dosage: "",
        frequency: "",
        refill_threshold: 5,
        pharmacy_id: "",
        notes: "",
      });
    }
    setError("");
  }, [medication, open]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const payload = {
        ...form,
        pharmacy_id: form.pharmacy_id || undefined,
        notes: form.notes || undefined,
      };
      if (isEdit && medication) {
        await api.updateMedication(medication.id, payload);
      } else {
        await api.createMedication(payload);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save medication";
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
      aria-label={isEdit ? "Edit medication" : "Add medication"}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-sand bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-sand px-6 py-4">
          <h3 className="font-serif text-lg text-forest">
            {isEdit ? "Edit Medication" : "Add Medication"}
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
            <label className="block text-sm font-medium text-charcoal">Medication name *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              placeholder="e.g. Lisinopril"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-charcoal">Dosage *</label>
              <input
                type="text"
                required
                value={form.dosage}
                onChange={(e) => setForm({ ...form, dosage: e.target.value })}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
                placeholder="e.g. 10mg"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-charcoal">Frequency *</label>
              <input
                type="text"
                required
                value={form.frequency}
                onChange={(e) => setForm({ ...form, frequency: e.target.value })}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
                placeholder="e.g. Once daily"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-charcoal">Refill threshold</label>
              <input
                type="number"
                min={1}
                max={30}
                value={form.refill_threshold}
                onChange={(e) =>
                  setForm({ ...form, refill_threshold: parseInt(e.target.value) || 5 })
                }
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-charcoal">Pharmacy ID</label>
              <input
                type="text"
                value={form.pharmacy_id}
                onChange={(e) => setForm({ ...form, pharmacy_id: e.target.value })}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-4 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
                placeholder="Optional"
              />
            </div>
          </div>

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
              {saving ? "Saving…" : isEdit ? "Update" : "Add Medication"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
