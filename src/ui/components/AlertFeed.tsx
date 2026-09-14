"use client";

import React from "react";
import { motion } from "framer-motion";
import type { AuditEvent } from "@/lib/api";
import {
  Bell,
  Pill,
  PackageCheck,
  Activity,
  CalendarCheck,
  PackageOpen,
  FileText,
  LogIn,
  UserPlus,
  Settings,
  CalendarPlus,
  GitBranch,
  type LucideIcon,
} from "lucide-react";

interface AlertFeedProps {
  events: AuditEvent[];
  onAck?: (id: string) => void;
  loading?: boolean;
}

function actionTypeToDisplay(
  action_type: string
): { title: string; icon: LucideIcon; category: string } {
  const mappings: Record<
    string,
    { title: string; icon: LucideIcon; category: string }
  > = {
    send_alert:              { title: "Alert sent to family",         icon: Bell,        category: "alert" },
    check_refill_status:     { title: "Refill status checked",        icon: Pill,        category: "medication" },
    order_refill:            { title: "Refill ordered",               icon: PackageCheck, category: "medication" },
    detect_adherence_pattern:{ title: "Adherence pattern checked",    icon: Activity,    category: "medication" },
    create_medication:       { title: "Medication added",             icon: Pill,        category: "medication" },
    schedule_appointment:    { title: "Appointment scheduled",        icon: CalendarCheck, category: "appointment" },
    create_appointment:      { title: "Appointment added",            icon: CalendarPlus, category: "appointment" },
    check_delivery_status:   { title: "Delivery status checked",      icon: PackageOpen, category: "logistics" },
    order_grocery:           { title: "Grocery order placed",         icon: PackageOpen, category: "logistics" },
    order_pharmacy_delivery: { title: "Pharmacy delivery ordered",    icon: PackageOpen, category: "logistics" },
    synthesize_status:       { title: "Daily status summary",         icon: FileText,    category: "supervisor" },
    process_event:           { title: "Supervisor routed event",      icon: GitBranch,   category: "supervisor" },
    login_firebase:          { title: "Caregiver signed in",          icon: LogIn,       category: "human" },
    onboard_new_user:        { title: "Caregiver onboarding complete", icon: UserPlus,   category: "human" },
    update_settings:         { title: "Settings updated",             icon: Settings,    category: "human" },
  };

  return (
    mappings[action_type] ?? {
      title: action_type.replace(/_/g, " "),
      icon: Activity,
      category: "default",
    }
  );
}

const CATEGORY_CLASSES: Record<string, string> = {
  alert:      "bg-terracotta/10 text-terracotta",
  medication: "bg-mint-light text-forest",
  appointment:"bg-sand-light text-forest",
  logistics:  "bg-sand text-forest",
  supervisor: "bg-forest/10 text-forest",
  human:      "bg-stone-200 text-stone-600",
  default:    "bg-mint-light text-forest",
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
        const display = actionTypeToDisplay(event.action_type);
        const Icon = display.icon;
        const colorClass = CATEGORY_CLASSES[display.category] ?? CATEGORY_CLASSES.default;
        return (
          <li
            key={event.event_id}
            className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start gap-3">
              <motion.div
                className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${colorClass}`}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </motion.div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-stone-900">
                    {display.title}
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
