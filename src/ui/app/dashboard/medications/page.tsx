"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type MedicationOut } from "@/lib/api";
import LoadingShimmer from "@/components/LoadingShimmer";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import ConfirmDialog from "@/components/ConfirmDialog";
import MedicationModal from "@/components/MedicationModal";
import { useToast } from "@/components/Toast";
import { Pill, Plus, Pencil, Trash2 } from "lucide-react";

export default function MedicationsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MedicationOut | null>(null);
  const [deleting, setDeleting] = useState<MedicationOut | null>(null);

  const { data: medications, isLoading, isError } = useQuery({
    queryKey: ["crud-medications"],
    queryFn: () => api.listMedications(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteMedication(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["crud-medications"] });
      showToast("Medication deleted", "success");
      setDeleting(null);
    },
    onError: () => {
      showToast("Failed to delete medication", "error");
    },
  });

  const handleEdit = (med: MedicationOut) => {
    setEditing(med);
    setModalOpen(true);
  };

  const handleAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["crud-medications"] });
    showToast(editing ? "Medication updated" : "Medication added", "success");
  };

  if (isLoading) return <LoadingShimmer lines={5} />;
  if (isError) return <ErrorState message="Could not load medications." onRetry={() => queryClient.invalidateQueries({ queryKey: ["crud-medications"] })} />;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-serif text-xl text-forest">Medications</h2>
        <button
          onClick={handleAdd}
          className="flex items-center gap-2 rounded-xl bg-forest px-4 py-2 text-sm font-medium text-cream shadow-sm transition-all hover:bg-forest-hover"
        >
          <Plus className="h-4 w-4" />
          Add medication
        </button>
      </div>

      {/* Table or empty */}
      {!medications || medications.length === 0 ? (
        <EmptyState
          title="No medications"
          description="No medications on record."
          action={
            <button
              onClick={handleAdd}
              className="flex items-center gap-2 rounded-xl bg-forest px-4 py-2 text-sm font-medium text-cream shadow-sm transition-all hover:bg-forest-hover"
            >
              <Plus className="h-4 w-4" />
              Add your first medication
            </button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-sand bg-white">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-sand text-left text-xs font-semibold uppercase tracking-wider text-muted">
                <th className="px-6 py-4">Name</th>
                <th className="px-6 py-4">Dosage</th>
                <th className="px-6 py-4">Frequency</th>
                <th className="px-6 py-4">Threshold</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sand">
              {medications.map((med) => (
                <tr key={med.id} className="transition-colors hover:bg-cream/50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Pill className="h-4 w-4 text-forest" aria-hidden="true" />
                      <span className="font-medium text-charcoal">{med.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-charcoal">{med.dosage}</td>
                  <td className="px-6 py-4 text-charcoal">{med.frequency}</td>
                  <td className="px-6 py-4 text-charcoal">{med.refill_threshold} days</td>
                  <td className="px-6 py-4">
                    <span className="rounded-full bg-mint-light px-2.5 py-0.5 text-xs font-medium text-forest">
                      Active
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleEdit(med)}
                        className="rounded-lg p-1.5 text-muted transition-colors hover:bg-sand-light hover:text-forest"
                        aria-label={`Edit ${med.name}`}
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleting(med)}
                        className="rounded-lg p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-red-600"
                        aria-label={`Delete ${med.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      <MedicationModal
        open={modalOpen}
        medication={editing}
        onClose={() => { setModalOpen(false); setEditing(null); }}
        onSaved={handleSaved}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Delete medication"
        message={`Are you sure you want to delete "${deleting?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
