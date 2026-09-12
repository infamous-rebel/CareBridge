"use client";

import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import LoadingShimmer from "@/components/LoadingShimmer";
import { ToastProvider } from "@/components/Toast";
import { useRouter } from "next/navigation";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function DashboardShell({ children }: { children: React.ReactNode }) {
  const { loading, user } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingShimmer lines={5} />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex min-h-screen bg-cream">
      <Sidebar />
      <div className="ml-60 flex-1">
        <TopBar />
        <main className="db-main overflow-y-auto p-8 pb-28">{children}</main>
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <DashboardShell>{children}</DashboardShell>
      </ToastProvider>
    </QueryClientProvider>
  );
}
