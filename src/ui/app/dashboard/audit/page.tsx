"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import AuditTrail from "@/components/AuditTrail";

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const [actor, setActor] = useState("");
  const [outcome, setOutcome] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit", page, actor, outcome],
    queryFn: () => api.getAudit(page, { actor: actor || undefined, outcome: outcome || undefined }),
  });

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-stone-900">Audit Trail</h2>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <select
          value={actor}
          onChange={(e) => { setActor(e.target.value); setPage(1); }}
          className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm text-stone-700 focus:border-forest-500 focus:outline-none"
          aria-label="Filter by actor"
        >
          <option value="">All actors</option>
          <option value="supervisor">Supervisor</option>
          <option value="medication">Medication</option>
          <option value="appointment">Appointment</option>
          <option value="logistics">Logistics</option>
          <option value="communication">Communication</option>
          <option value="human">Human</option>
        </select>
        <select
          value={outcome}
          onChange={(e) => { setOutcome(e.target.value); setPage(1); }}
          className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm text-stone-700 focus:border-forest-500 focus:outline-none"
          aria-label="Filter by outcome"
        >
          <option value="">All outcomes</option>
          <option value="success">Success</option>
          <option value="failure">Failure</option>
          <option value="pending">Pending</option>
          <option value="escalated">Escalated</option>
        </select>
      </div>

      <AuditTrail
        data={data}
        page={page}
        onPageChange={setPage}
        loading={isLoading}
      />
    </div>
  );
}
