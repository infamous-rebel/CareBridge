"use client";

import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import LoadingShimmer from "@/components/LoadingShimmer";
import ErrorState from "@/components/ErrorState";
import { useToast } from "@/components/Toast";
import { Bell, Mail, Smartphone, Clock, Globe } from "lucide-react";

const TZ_IDS = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "America/Mexico_City",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Moscow",
  "Asia/Dhaka",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
  "Pacific/Auckland",
];

function getTzOffset(tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en", {
      timeZone: tz,
      timeZoneName: "shortOffset",
    })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName");
    return parts?.value ?? "GMT";
  } catch {
    return "GMT";
  }
}

function buildTimezones() {
  return TZ_IDS.map((tz) => ({
    value: tz,
    label: `${tz} (${getTzOffset(tz)})`,
  }));
}

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "zh", label: "中文" },
];

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const { data: settings, isLoading, isError } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  /* ── local form state ────────────────────────────────────────────── */
  const [sms, setSms] = useState(true);
  const [email, setEmail] = useState(true);
  const [digest, setDigest] = useState(true);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("07:00");
  const [timezone, setTimezone] = useState("UTC");
  const [language, setLanguage] = useState("en");

  /* hydrate from API once loaded */
  useEffect(() => {
    if (settings) {
      const prefs = settings.notification_prefs;
      setSms(prefs.sms ?? true);
      setEmail(prefs.email ?? true);
      setDigest(prefs.daily_digest ?? true);
      setQuietStart(settings.quiet_hours_start ?? "22:00");
      setQuietEnd(settings.quiet_hours_end ?? "07:00");
      setLanguage(settings.language ?? "en");

      /* Auto-detect browser timezone when backend returns the default 'UTC'
         and the user has never saved a preference. */
      const savedTz = settings.timezone;
      if (savedTz && savedTz !== "UTC") {
        setTimezone(savedTz);
      } else {
        const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
        setTimezone(TZ_IDS.includes(detected) ? detected : "UTC");
      }
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateSettings({
        notification_prefs: { sms, email, daily_digest: digest },
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
        timezone,
        language,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      showToast("Settings saved", "success");
    },
    onError: () => {
      showToast("Failed to save settings", "error");
    },
  });

  if (isLoading) return <LoadingShimmer lines={6} />;
  if (isError) return <ErrorState message="Could not load settings." onRetry={() => queryClient.invalidateQueries({ queryKey: ["settings"] })} />;

  return (
    <div>
      <h2 className="mb-6 font-serif text-xl text-forest">Settings</h2>

      <div className="max-w-lg space-y-6">
        {/* ── Notification Preferences ───────────────────────────────── */}
        <div className="rounded-2xl border border-sand bg-white p-6">
          <h3 className="text-sm font-semibold text-charcoal">Notification Preferences</h3>
          <p className="mt-1 text-xs text-muted">
            Choose how you want to receive alerts and updates.
          </p>

          <div className="mt-4 space-y-3">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={sms}
                onChange={(e) => setSms(e.target.checked)}
                className="h-4 w-4 rounded border-sand text-forest focus:ring-forest"
              />
              <Smartphone className="h-4 w-4 text-muted" aria-hidden="true" />
              <span className="text-sm text-charcoal">SMS alerts for critical events</span>
            </label>

            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={email}
                onChange={(e) => setEmail(e.target.checked)}
                className="h-4 w-4 rounded border-sand text-forest focus:ring-forest"
              />
              <Mail className="h-4 w-4 text-muted" aria-hidden="true" />
              <span className="text-sm text-charcoal">Email notifications</span>
            </label>

            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={digest}
                onChange={(e) => setDigest(e.target.checked)}
                className="h-4 w-4 rounded border-sand text-forest focus:ring-forest"
              />
              <Bell className="h-4 w-4 text-muted" aria-hidden="true" />
              <span className="text-sm text-charcoal">Daily digest summary</span>
            </label>
          </div>
        </div>

        {/* ── Quiet Hours ────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-sand bg-white p-6">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-charcoal">
            <Clock className="h-4 w-4 text-muted" />
            Quiet Hours
          </h3>
          <p className="mt-1 text-xs text-muted">
            Suppress non-critical notifications during these hours.
          </p>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-charcoal">Start</label>
              <input
                type="time"
                value={quietStart}
                onChange={(e) => setQuietStart(e.target.value)}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-3 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-charcoal">End</label>
              <input
                type="time"
                value={quietEnd}
                onChange={(e) => setQuietEnd(e.target.value)}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-3 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              />
            </div>
          </div>
        </div>

        {/* ── Region & Language ──────────────────────────────────────── */}
        <div className="rounded-2xl border border-sand bg-white p-6">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-charcoal">
            <Globe className="h-4 w-4 text-muted" />
            Region & Language
          </h3>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-charcoal">Timezone</label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-3 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              >
                {buildTimezones().map((tz) => (
                  <option key={tz.value} value={tz.value}>{tz.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-charcoal">Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="mt-1 w-full rounded-lg border border-sand bg-white px-3 py-2 text-sm text-charcoal focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* ── Save ──────────────────────────────────────────────────── */}
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="rounded-xl bg-forest px-5 py-2.5 text-sm font-semibold text-cream transition-colors hover:bg-forest-hover disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : "Save preferences"}
        </button>
      </div>
    </div>
  );
}
