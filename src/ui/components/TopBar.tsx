"use client";

import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { LogOut } from "lucide-react";

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function TopBar() {
  const { user, logout } = useAuth();
  const [greeting, setGreeting] = useState(getGreeting);

  useEffect(() => {
    const id = setInterval(() => setGreeting(getGreeting()), 60_000);
    return () => clearInterval(id);
  }, []);

  const { data: ready } = useQuery({
    queryKey: ["ready"],
    queryFn: () => api.getReady(),
    staleTime: 30_000,
    retry: 1,
  });

  const name = user?.full_name ?? "Caregiver";
  const systemLabel = ready?.llm_available ? "All systems nominal" : "Degraded mode";

  return (
    <header className="flex h-20 flex-shrink-0 items-center justify-between border-b border-sand bg-cream px-8">
      <div className="min-w-0">
        <h1 className="whitespace-nowrap font-serif text-2xl font-normal text-forest sm:text-3xl truncate">
          {greeting}, {name}
        </h1>
      </div>

      <div className="flex items-center gap-6">
        {/* System status */}
        <div className="flex items-center gap-2.5 rounded-full border border-sand bg-white px-3.5 py-1.5 text-xs font-medium text-charcoal shadow-sm">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-mint status-pulse" />
          <span>{systemLabel}</span>
        </div>

        <button
          onClick={logout}
          className="flex items-center gap-1.5 text-xs font-medium text-muted transition-colors hover:text-forest"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign Out
        </button>
      </div>
    </header>
  );
}
