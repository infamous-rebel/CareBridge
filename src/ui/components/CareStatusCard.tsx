"use client";

import React from "react";
import type { StatusSummary, Medication, Appointment } from "@/lib/api";
import { Pill, CalendarDays } from "lucide-react";

interface CareStatusCardProps {
  summary: StatusSummary | undefined;
  medications: Medication[] | undefined;
  appointments: Appointment[] | undefined;
  name: string;
  age: number;
  address: string;
}

export default function CareStatusCard({
  medications,
  appointments,
  name,
  age,
  address,
}: CareStatusCardProps) {
  const medCount = medications?.length ?? 0;
  const nextAppt = appointments?.[0];

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-6 md:flex-row">
        {/* Profile */}
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-mint-100 text-2xl font-bold text-forest-600">
            {name.charAt(0)}
          </div>
          <div>
            <h2 className="text-xl font-semibold text-stone-900">{name}</h2>
            <p className="text-sm text-muted">
              Age {age} · {address}
            </p>
            <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
              Health Synced
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="flex flex-1 items-center justify-around border-t border-stone-100 pt-4 md:border-0 md:border-l md:pt-0">
          <div className="text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">
              Current Medications
            </p>
            <p className="mt-1 flex items-center justify-center gap-1 font-serif text-2xl font-bold text-forest-600">
              <Pill className="h-4 w-4" aria-hidden="true" />
              {medCount}
            </p>
            <p className="text-xs text-muted">active</p>
          </div>
          <div className="text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">
              Next Appointment
            </p>
            {nextAppt ? (
              <>
                <p className="mt-1 flex items-center justify-center gap-1 font-serif text-lg font-semibold text-stone-900">
                  <CalendarDays className="h-4 w-4 text-forest-600" aria-hidden="true" />
                  {nextAppt.specialty}
                </p>
                <p className="text-xs text-muted">
                  {new Date(nextAppt.datetime).toLocaleDateString("en-US", {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                  })}{" "}
                  · {new Date(nextAppt.datetime).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
                </p>
              </>
            ) : (
              <p className="mt-1 text-sm text-muted">None scheduled</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
