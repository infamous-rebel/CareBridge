"use client";

import React from "react";
import {
  Home,
  Pill,
  CalendarDays,
  Truck,
  Bell,
  ClipboardCheck,
  ScrollText,
  Settings,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: Home },
  { label: "Medications", href: "/dashboard/medications", icon: Pill },
  { label: "Appointments", href: "/dashboard/appointments", icon: CalendarDays },
  { label: "Deliveries", href: "/dashboard/deliveries", icon: Truck },
  { label: "Alerts", href: "/dashboard/alerts", icon: Bell },
  { label: "Approvals", href: "/dashboard/approvals", icon: ClipboardCheck },
  { label: "Audit Trail", href: "/dashboard/audit", icon: ScrollText },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const initials = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()
    : "CB";

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-full w-60 flex-shrink-0 flex-col justify-between border-r border-sand bg-sidebar-bg select-none">
      <div>
        {/* Logo */}
        <Link href="/dashboard" className="flex h-20 items-center gap-3 border-b border-sand px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-forest font-serif text-sm font-bold text-cream shadow-sm">
            CB
          </div>
          <span className="font-serif text-xl font-semibold tracking-tight text-forest">CareBridge</span>
        </Link>

        {/* Navigation */}
        <nav className="space-y-1 p-4 text-sm font-medium" aria-label="Dashboard navigation">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3.5 py-2.5 transition-colors",
                  isActive
                    ? "bg-mint-light text-forest"
                    : "text-muted hover:bg-sand/40 hover:text-forest",
                )}
                aria-current={isActive ? "page" : undefined}
              >
                <item.icon className="w-5 flex-shrink-0 text-center" aria-hidden="true" />
                <span>{item.label}</span>
                {item.badge && (
                  <span className="ml-auto rounded-full bg-forest px-1.5 py-0.5 text-[10px] font-semibold text-cream">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* User profile */}
      <div className="border-t border-sand p-4">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-sand font-serif text-sm font-bold text-forest">
            {initials}
          </div>
          <div className="overflow-hidden">
            <div className="truncate text-xs font-semibold text-charcoal">
              {user?.full_name ?? "Caregiver"}
            </div>
            <div className="truncate text-[11px] text-muted">
              {user?.role === "caregiver_primary" ? "Primary Caregiver" : user?.role ?? "Viewer"}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
