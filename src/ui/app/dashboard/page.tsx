"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import LoadingShimmer from "@/components/LoadingShimmer";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import {
  Video,
  Pill,
  CalendarPlus,
  Share2,
  Zap,
  ArrowUp,
  Mic,
  Shield,
  Check,
  X,
} from "lucide-react";

const CARE_RECIPIENT_ID = "cr-001";

/* ── helpers ─────────────────────────────────────────────────────────── */

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const ACTIVITY_ICON: Record<string, string> = {
  order_refill: "fa-pills",
  schedule_appointment: "fa-stethoscope",
  check_refill_status: "fa-pills",
  send_alert: "fa-bell",
  send_sms: "fa-envelope",
  send_email: "fa-envelope",
};

/* ── Family Action modal ─────────────────────────────────────────────── */
function ActionModal({
  action,
  onClose,
}: {
  action: string | null;
  onClose: () => void;
}) {
  if (!action) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-charcoal/40 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md rounded-2xl border border-sand bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-sand pb-3">
          <h3 className="font-serif text-lg text-forest">
            {action} — CareBridge Agent
          </h3>
          <button
            onClick={onClose}
            className="text-muted hover:text-forest text-sm"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-charcoal">
          The autonomous supervisor agent is securely initiating{" "}
          {action.toLowerCase()} for Evelyn Smith. You will receive an encrypted
          status update within 60 seconds.
        </p>
        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-xl bg-forest px-5 py-2.5 text-xs font-medium text-cream hover:bg-forest-hover"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   DASHBOARD OVERVIEW
   ═══════════════════════════════════════════════════════════════════════ */
export default function DashboardOverview() {
  const queryClient = useQueryClient();
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [modalAction, setModalAction] = useState<string | null>(null);

  /* ── data hooks ──────────────────────────────────────────────────── */
  const {
    data: status,
    isLoading: statusLoading,
    isError: statusError,
  } = useQuery({
    queryKey: ["status", CARE_RECIPIENT_ID],
    queryFn: () => api.getStatus(CARE_RECIPIENT_ID),
    refetchInterval: 30_000,
  });

  const {
    data: medications,
    isLoading: medsLoading,
  } = useQuery({
    queryKey: ["medications", CARE_RECIPIENT_ID],
    queryFn: () => api.getMedications(CARE_RECIPIENT_ID),
  });

  const {
    data: appointments,
    isLoading: apptsLoading,
  } = useQuery({
    queryKey: ["appointments", CARE_RECIPIENT_ID],
    queryFn: () => api.getAppointments(CARE_RECIPIENT_ID, 90),
  });

  const {
    data: alerts,
    isLoading: alertsLoading,
  } = useQuery({
    queryKey: ["alerts", CARE_RECIPIENT_ID],
    queryFn: () => api.getAlerts(CARE_RECIPIENT_ID),
    refetchInterval: 5_000,
  });

  const {
    data: approvals,
    isLoading: approvalsLoading,
  } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.getApprovals(),
    refetchInterval: 10_000,
  });

  /* ── mutations ───────────────────────────────────────────────────── */
  const approveMutation = useMutation({
    mutationFn: (id: string) => api.approveAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.rejectAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  /* ── chat handler ────────────────────────────────────────────────── */
  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    setChatLoading(true);
    try {
      const res = await api.query(CARE_RECIPIENT_ID, chatInput);
      setModalAction(`Query: "${chatInput}"`);
      void res;
    } catch {
      setModalAction("Query — Error");
    } finally {
      setChatLoading(false);
      setChatInput("");
    }
  };

  /* ── derived ─────────────────────────────────────────────────────── */
  const medCount = medications?.length ?? 0;
  const nextAppt = appointments?.[0];
  const pendingCount = approvals?.filter((a) => a.status === "pending").length ?? 0;
  const careLoading = statusLoading || medsLoading || apptsLoading;

  /* ── render ──────────────────────────────────────────────────────── */
  return (
    <>
      {/* ── Care Recipient Card ──────────────────────────────────────── */}
      {careLoading ? (
        <LoadingShimmer lines={4} className="h-36" />
      ) : statusError ? (
        <ErrorState message="Could not load care recipient data." onRetry={() => queryClient.invalidateQueries({ queryKey: ["status"] })} />
      ) : (
        <section className="flex flex-col items-start justify-between gap-6 rounded-2xl border border-sand bg-white p-6 sm:p-8 lg:flex-row lg:items-center">
          {/* Left: avatar + info */}
          <div className="flex items-start space-x-5 sm:items-center">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-mint/40 bg-mint-light font-serif text-3xl font-bold text-forest sm:h-20 sm:w-20">
              E
            </div>
            <div className="space-y-1">
              <div className="flex items-center space-x-3">
                <h2 className="font-serif text-2xl font-normal text-forest sm:text-[28px]">
                  {status?.care_recipient_id ? "Evelyn Smith" : "Care Recipient"}
                </h2>
                <span className="flex items-center space-x-1.5 rounded-full border border-mint/30 bg-mint-light px-3 py-1 text-xs font-medium text-forest">
                  <Shield className="h-2.5 w-2.5" />
                  <span>Health Synced</span>
                </span>
              </div>
              <p className="text-sm text-muted">
                Age 78 · 124 Oakridge Lane
              </p>
            </div>
          </div>

          {/* Right: metrics */}
          <div className="flex w-full flex-wrap items-center gap-4 border-t border-sand pt-4 lg:w-auto lg:border-0 lg:pt-0 lg:flex-nowrap">
            <div className="flex-1 rounded-xl border border-sand bg-cream p-4 sm:w-56">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
                Current Medications
              </div>
              <div className="flex items-baseline space-x-2">
                <span className="font-serif text-3xl font-normal text-forest">
                  {medCount}
                </span>
                <span className="text-xs text-muted">active prescriptions</span>
              </div>
            </div>
            <div className="flex-1 rounded-xl border border-sand bg-cream p-4 sm:w-64">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
                Next Appointment
              </div>
              {nextAppt ? (
                <>
                  <div className="truncate font-serif text-lg font-normal text-forest">
                    {nextAppt.specialty}
                  </div>
                  <div className="mt-0.5 text-xs font-medium text-muted">
                    {new Date(nextAppt.datetime).toLocaleDateString("en-US", { weekday: "short" })}{" · "}
                    <span className="font-serif text-sm font-semibold text-forest">
                      {new Date(nextAppt.datetime).toLocaleTimeString("en-US", {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted">None scheduled</div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── Grid: Activity Feed + Right Column ──────────────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Recent Activity Feed — 8 cols */}
        <div className="flex flex-col justify-between rounded-2xl border border-sand bg-white p-6 sm:p-8 lg:col-span-8">
          <div>
            <div className="flex items-center justify-between border-b border-sand pb-6 mb-6">
              <div className="flex items-center space-x-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-mint-light text-forest text-sm">
                  <Zap className="h-4 w-4" />
                </div>
                <h3 className="font-serif text-xl font-normal text-forest">
                  Recent Activity Feed
                </h3>
              </div>
              <span className="text-xs font-medium text-muted">
                Live Supervisor Log
              </span>
            </div>

            {alertsLoading ? (
              <LoadingShimmer lines={4} />
            ) : !alerts || alerts.length === 0 ? (
              <EmptyState title="No recent activity" description="Everything looks calm." />
            ) : (
              <div className="space-y-4">
                {alerts.slice(0, 8).map((event) => (
                  <div
                    key={event.event_id}
                    className="flex items-start space-x-4 border-b border-sand pb-4 last:border-0 last:pb-0"
                  >
                    <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-mint-light text-forest text-sm">
                      {ACTIVITY_ICON[event.action_type] ? (
                        <i className={`fa-solid ${ACTIVITY_ICON[event.action_type]}`} />
                      ) : (
                        <Zap className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-semibold text-charcoal">
                          {event.action_type.replace(/_/g, " ")}
                        </h4>
                        <span className="font-mono text-xs text-muted">
                          {timeAgo(event.timestamp)}
                        </span>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-muted">
                        {event.rationale}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column — 4 cols */}
        <div className="space-y-6 lg:col-span-4">
          {/* Needs Approval */}
          <div className="rounded-2xl border border-sand bg-white p-6 sm:p-8">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
                <h3 className="font-serif text-lg font-normal text-forest">
                  Needs Approval
                </h3>
              </div>
              {pendingCount > 0 && (
                <span className="rounded-full bg-sand/60 px-2.5 py-0.5 text-[11px] font-semibold text-charcoal">
                  {pendingCount} Pending
                </span>
              )}
            </div>

            {approvalsLoading ? (
              <LoadingShimmer lines={2} />
            ) : !approvals || approvals.filter((a) => a.status === "pending").length === 0 ? (
              <EmptyState title="No pending approvals" description="You&apos;re all caught up." />
            ) : (
              approvals
                .filter((a) => a.status === "pending")
                .slice(0, 1)
                .map((action) => (
                  <div key={action.action_id}>
                    <div className="mb-5 rounded-xl border border-sand bg-cream p-4 space-y-3">
                      <div className="text-xs font-bold uppercase tracking-wider text-forest">
                        {action.action_type.replace(/_/g, " ")}
                      </div>
                      <p className="text-sm font-medium text-charcoal">
                        {action.rationale}
                      </p>
                      <div className="text-[11px] text-muted">
                        Supervisor agent verified. Ready for approval.
                      </div>
                    </div>
                    <div className="flex items-center space-x-3">
                      <button
                        onClick={() => approveMutation.mutate(action.action_id)}
                        disabled={approveMutation.isPending}
                        className="flex flex-1 items-center justify-center space-x-1.5 rounded-xl bg-forest px-4 py-2.5 text-xs font-medium text-cream shadow-sm transition-all hover:bg-forest-hover disabled:opacity-50"
                      >
                        <Check className="h-3.5 w-3.5" />
                        <span>Approve</span>
                      </button>
                      <button
                        onClick={() => rejectMutation.mutate(action.action_id)}
                        disabled={rejectMutation.isPending}
                        className="flex flex-1 items-center justify-center space-x-1.5 rounded-xl border border-sand bg-transparent px-4 py-2.5 text-xs font-medium text-charcoal transition-all hover:bg-sand/30 disabled:opacity-50"
                      >
                        <X className="h-3.5 w-3.5" />
                        <span>Reject</span>
                      </button>
                    </div>
                  </div>
                ))
            )}
          </div>

          {/* Family Actions 2×2 */}
          <div className="rounded-2xl border border-sand bg-white p-6 sm:p-8">
            <h3 className="mb-4 font-serif text-lg font-normal text-forest">
              Family Actions
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Video Call", icon: Video },
                { label: "Order Meds", icon: Pill },
                { label: "Book Visit", icon: CalendarPlus },
                { label: "Share Records", icon: Share2 },
              ].map((a) => (
                <button
                  key={a.label}
                  onClick={() => setModalAction(a.label)}
                  className="group flex flex-col items-center justify-center space-y-2 rounded-xl border border-sand bg-cream p-4 transition-all hover:border-forest"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-mint-light text-forest transition-transform group-hover:scale-105">
                    <a.icon className="h-4 w-4" />
                  </div>
                  <span className="text-xs font-semibold text-charcoal">
                    {a.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom Fixed Chat Bar ────────────────────────────────────── */}
      <div className="fixed bottom-0 left-60 right-0 z-30 border-t border-sand bg-cream/90 px-8 py-4 backdrop-blur-md">
        <div className="mx-auto max-w-4xl">
          <form onSubmit={handleChat} className="relative flex items-center">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask about Mom..."
              className="w-full rounded-full border border-sand bg-white py-3.5 pl-5 pr-24 text-sm text-charcoal placeholder-muted shadow-sm focus:border-forest focus:outline-none"
              aria-label="Ask a question about your care recipient"
            />
            <div className="absolute right-2.5 flex items-center space-x-1.5">
              <button
                type="button"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-sand/60 text-charcoal transition-colors hover:bg-forest hover:text-cream"
                title="Voice Input"
                aria-label="Voice input"
              >
                <Mic className="h-4 w-4" />
              </button>
              <button
                type="submit"
                disabled={chatLoading || !chatInput.trim()}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-forest text-cream shadow-sm transition-colors hover:bg-forest-hover disabled:opacity-50"
                title="Send"
                aria-label="Send"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* ── Action Modal ─────────────────────────────────────────────── */}
      <ActionModal action={modalAction} onClose={() => setModalAction(null)} />
    </>
  );
}
