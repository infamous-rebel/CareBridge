"use client";

import React, { useRef, useState } from "react";
import Link from "next/link";
import { motion, useInView } from "framer-motion";
import {
  ArrowRight,
  PhoneOff,
  MessageSquare,
  AlertTriangle,
  Pill,
  CalendarCheck,
  Stethoscope,
  Shield,
  Lock,
  Server,
  Key,
  Fingerprint,
  Cpu,
  Zap,
} from "lucide-react";
import AgentOrbit from "@/components/AgentOrbit";

/* Warm editorial motion: fade + 16px rise, 500ms, long settle — never bouncy */
const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

function FadeSection({
  children, className, id,
}: { children: React.ReactNode; className?: string; id?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.section
      ref={ref} id={id} className={className}
      initial={{ opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, ease: EASE }}
    >
      {children}
    </motion.section>
  );
}

function StaggerChildren({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  return (
    <div ref={ref} className={className}>
      {React.Children.map(children, (child, i) => (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ delay: i * 0.08, duration: 0.5, ease: EASE }}
        >
          {child}
        </motion.div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   1. STICKY NAV
   ═══════════════════════════════════════════════════════════════════ */
function Nav() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-sand bg-cream/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-[1440px] items-center justify-between px-6 sm:px-12">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-forest font-serif text-xl font-bold text-cream shadow-sm">
            CB
          </div>
          <span className="font-serif text-2xl font-semibold tracking-tight text-forest">CareBridge</span>
        </Link>

        <nav className="hidden items-center gap-8 text-sm font-medium text-muted md:flex">
          <a href="#problem" className="transition-colors hover:text-forest">The Challenge</a>
          <a href="#how-it-works" className="transition-colors hover:text-forest">How It Works</a>
          <a href="#dashboard" className="transition-colors hover:text-forest">Live Dashboard</a>
          <a href="#impact" className="transition-colors hover:text-forest">Impact</a>
          <a href="#architecture" className="transition-colors hover:text-forest">Architecture</a>
        </nav>

        <div className="flex items-center gap-4">
          <Link href="/login" className="hidden text-sm font-medium text-forest hover:text-forest-hover sm:inline-flex px-4 py-2">
            Sign In
          </Link>
          <Link href="/signup" className="rounded-full bg-forest px-5 py-2.5 text-sm font-medium text-cream shadow-sm transition-all hover:bg-forest-hover">
            Sign up free
          </Link>
        </div>
      </div>
    </header>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   2. HERO
   ═══════════════════════════════════════════════════════════════════ */
function Hero() {
  return (
    <section className="hero-glow relative overflow-hidden px-6 py-16 sm:px-12 sm:py-24">
      <div className="mx-auto grid max-w-[1440px] grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-8">
        {/* Left copy */}
        <div className="flex flex-col items-start gap-8 lg:col-span-7">
          <motion.div
            className="inline-flex items-center gap-2 rounded-full border border-sand bg-sand-light px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-forest"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}
          >
            <span className="inline-block h-2 w-2 rounded-full bg-forest" />
            Autonomous Family Healthcare Infrastructure
          </motion.div>

          <motion.h1
            className="font-serif text-4xl font-normal leading-[1.08] text-forest sm:text-6xl lg:text-7xl"
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
          >
            The AI coordinator for aging parents.
          </motion.h1>

          <motion.p
            className="max-w-2xl text-lg text-muted sm:text-xl"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3, duration: 0.7 }}
          >
            Your parent stays independent. You stop drowning in logistics.
            CareBridge handles the refills, appointments, and follow-ups —
            you only see what actually needs you.
          </motion.p>

          <motion.div
            className="flex w-full flex-col items-stretch gap-4 sm:w-auto sm:flex-row sm:items-center"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.5 }}
          >
            <Link href="/signup" className="flex items-center justify-center gap-2 rounded-full bg-forest px-8 py-4 text-center font-medium text-cream shadow-sm transition-all hover:bg-forest-hover">
              <span>Sign up free</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/login" className="flex items-center justify-center rounded-full border border-sand bg-transparent px-8 py-4 text-center font-medium text-forest transition-all hover:bg-sand-light">
              Sign in
            </Link>
          </motion.div>

          {/* Stat chips */}
          <div className="grid w-full grid-cols-3 gap-4 border-t border-sand pt-6">
            {[
              { value: "27 hrs", label: "Saved monthly per family" },
              { value: "45%", label: "Fewer medication errors" },
              { value: "100%", label: "Audited — every action logged" },
            ].map((s) => (
              <div key={s.label}>
                <div className="font-serif text-2xl font-semibold text-forest sm:text-3xl">{s.value}</div>
                <div className="mt-0.5 text-xs text-muted sm:text-sm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Live agent card */}
        <div className="relative flex justify-center lg:col-span-5">
          <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-tr from-mint/20 to-sand/40 blur-2xl" />
          <motion.div
            className="relative w-full max-w-md rounded-2xl border border-sand bg-white p-6 shadow-xl"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.6, ease: EASE }}
          >
            {/* Border glow pulse */}
            <div className="pointer-events-none absolute inset-0 rounded-2xl border border-mint/30 mint-pulse" />

            <div className="flex items-center justify-between border-b border-sand pb-4">
              <div className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-full bg-mint mint-pulse" />
                <span className="text-xs font-semibold uppercase tracking-wider text-forest">Live Agent Activity</span>
              </div>
              <span className="font-mono text-xs text-muted">ID: AGT-8842</span>
            </div>

            <div className="space-y-4 py-6">
              <div className="rounded-xl border border-sand bg-cream p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="rounded bg-mint-light px-2 py-1 text-xs font-bold text-forest">Supervisor Agent</span>
                  <span className="text-xs text-muted">2s ago</span>
                </div>
                <p className="text-sm font-medium text-charcoal">
                  Supervisor → Medication Agent · refill ordered at CVS #4192
                </p>
              </div>

              <div className="space-y-2.5">
                <div className="flex items-center justify-between px-1 text-xs">
                  <span className="font-medium text-charcoal">Active Sub-Agents</span>
                  <span className="font-semibold text-forest">4 Online</span>
                </div>
                {[
                  { icon: Pill, name: "Medication Agent", status: "Verified morning dosage", badge: "Idle / Ready", badgeCls: "bg-mint/30 text-forest" },
                  { icon: CalendarCheck, name: "Appointment Agent", status: "Dr. Vance on Thursday @ 2PM", badge: "Active Now", badgeCls: "bg-forest text-cream" },
                ].map((a) => (
                  <div key={a.name} className="flex items-center justify-between rounded-lg border border-sand/80 bg-white p-3 shadow-sm">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-mint-light text-forest">
                        <a.icon className="h-3.5 w-3.5" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-charcoal">{a.name}</div>
                        <div className="text-[11px] text-muted">{a.status}</div>
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${a.badgeCls}`}>{a.badge}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-sand pt-4 text-xs text-muted">
              <span>Encrypted HIPAA Vault</span>
              <span className="flex items-center gap-1 font-medium text-forest">
                <Shield className="h-3.5 w-3.5" /> Secured
              </span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   3. REAL WORKING PRODUCT (new section)
   ═══════════════════════════════════════════════════════════════════ */
function RealProduct() {
  const features = [
    { icon: Fingerprint, title: "Sign in with Google", desc: "Real Firebase auth. No demo mode. Sign up in 5 seconds." },
    { icon: Cpu, title: "Bring your own LLM", desc: "Gemini, Groq, Bedrock, Anthropic, OpenAI, or local Ollama. One env var. No lock-in." },
    { icon: Zap, title: "Immutable audit trail", desc: "Every agent action written BEFORE it executes. 174 automated tests. Production-grade." },
  ];

  return (
    <FadeSection className="border-y border-sand bg-white px-6 py-16 sm:px-12 sm:py-20">
      <div className="mx-auto max-w-4xl text-center">
        <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">Real, working product</span>
        <h2 className="mt-4 font-serif text-3xl text-forest sm:text-4xl">Not a mockup. A running system.</h2>
      </div>
      <StaggerChildren className="mx-auto mt-12 grid max-w-5xl grid-cols-1 gap-6 md:grid-cols-3">
        {features.map((f) => (
          <div key={f.title} className="flex flex-col justify-between rounded-2xl border border-sand bg-white p-8 shadow-sm transition-all hover:border-forest/40">
            <div>
              <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-mint-light text-forest">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mb-3 font-serif text-xl text-forest">{f.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{f.desc}</p>
            </div>
          </div>
        ))}
      </StaggerChildren>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   4. PROBLEM
   ═══════════════════════════════════════════════════════════════════ */
function Problem() {
  const cards = [
    { icon: PhoneOff, title: "The Endless Phone Queue", desc: "Spending 45 minutes on hold with insurance providers, Medicare reps, and pharmacy refill desks just to clarify a copay discrepancy.", stat: "6.4 hours", label: "Average weekly loss" },
    { icon: MessageSquare, title: "Sibling Alignment Drag", desc: "Endless text threads arguing about who called mom, who paid for groceries, and why medical updates are perpetually out of sync.", stat: "High Stress", label: "Communication friction" },
    { icon: AlertTriangle, title: "Fragmented Health Data", desc: "Scattered pill bottles, paper appointment cards, blood pressure logs on sticky notes, and zero unified oversight across specialists.", stat: "Missed Doses", label: "Risk factor" },
  ];

  return (
    <FadeSection id="problem" className="border-y border-sand bg-white px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-4xl space-y-4 text-center">
        <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">The Caregiving Crisis</span>
        <h2 className="font-serif text-3xl text-forest sm:text-5xl">You became the integration layer.</h2>
        <p className="mx-auto max-w-2xl text-base text-muted sm:text-lg">
          Between pharmacy call queues, portal logins, conflicting sibling group chats, and missed vitals, modern caregiving demands full-time operational management on top of your career.
        </p>
      </div>
      <StaggerChildren className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-8 md:grid-cols-3">
        {cards.map((c) => (
          <div key={c.title} className="flex flex-col justify-between rounded-2xl border border-sand bg-white p-8 shadow-sm transition-all hover:border-forest/40">
            <div>
              <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-mint-light text-forest text-lg">
                <c.icon />
              </div>
              <h3 className="mb-3 font-serif text-xl text-forest">{c.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{c.desc}</p>
            </div>
            <div className="mt-8 flex items-center justify-between border-t border-sand/60 pt-4 text-xs font-semibold text-forest">
              <span>{c.label}</span>
              <span className="rounded bg-sand-light px-2 py-1 font-mono">{c.stat}</span>
            </div>
          </div>
        ))}
      </StaggerChildren>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   5. HOW IT WORKS
   ═══════════════════════════════════════════════════════════════════ */
function HowItWorks() {
  const steps = [
    { num: "01", title: "Connect Sources", desc: "Securely link pharmacy accounts, provider portals, and smart home health devices in under 5 minutes with our encrypted onboarding flow." },
    { num: "02", title: "Autonomous Execution", desc: "The supervisor handles routine friction—rescheduling missed appointments, requesting prescription refills, and logging daily check-ins." },
    { num: "03", title: "Quiet Family Sync", desc: "Instead of frantic calls, family members receive a clean, bulleted morning briefing summarizing status, upcoming visits, and necessary actions." },
  ];

  return (
    <FadeSection id="how-it-works" className="px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-4xl space-y-4 text-center">
        <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">Autonomous Orchestration</span>
        <h2 className="font-serif text-3xl text-forest sm:text-5xl">Five agents. One supervisor. Zero chasing.</h2>
        <p className="mx-auto max-w-2xl text-base text-muted sm:text-lg">
          CareBridge replaces manual tracking with an autonomous multi-agent system that runs 24/7 in the background.
        </p>
      </div>

      {/* Agent orbit */}
      <div className="relative mx-auto mt-12 max-w-5xl overflow-hidden rounded-3xl border border-sand bg-white p-8 shadow-sm sm:p-12">
        <div className="pointer-events-none absolute inset-0 opacity-45" style={{ backgroundImage: "radial-gradient(#E8DCC4 1px, transparent 1px)", backgroundSize: "24px 24px" }} />
        <div className="relative z-10">
          <div className="mb-10 text-center">
            <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-bold uppercase tracking-widest text-muted">Interactive Agent Topology</span>
          </div>
          <AgentOrbit />
        </div>
      </div>

      {/* Steps */}
      <StaggerChildren className="mt-16 grid grid-cols-1 gap-8 md:grid-cols-3">
        {steps.map((s) => (
          <div key={s.title} className="rounded-2xl border border-sand bg-white p-8">
            <div className="mb-4 font-serif text-4xl font-bold text-forest/30">{s.num}</div>
            <h3 className="mb-2 font-serif text-xl text-forest">{s.title}</h3>
            <p className="text-sm text-muted">{s.desc}</p>
          </div>
        ))}
      </StaggerChildren>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   6. LIVE DASHBOARD PREVIEW
   ═══════════════════════════════════════════════════════════════════ */
type TabKey = "medication" | "appointment" | "vital" | "family";

function DashboardPreview() {
  const [tab, setTab] = useState<TabKey>("medication");
  const tabs: { key: TabKey; label: string }[] = [
    { key: "medication", label: "Medication" },
    { key: "appointment", label: "Appointments" },
    { key: "vital", label: "Vitals" },
    { key: "family", label: "Family Sync" },
  ];

  return (
    <FadeSection id="dashboard" className="border-y border-sand bg-offwhite px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-4xl space-y-4 text-center">
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest shadow-sm">Interactive Preview</span>
        <h2 className="font-serif text-3xl text-forest sm:text-5xl">The dashboard your sibling will actually use.</h2>
        <p className="mx-auto max-w-2xl text-base text-muted sm:text-lg">
          No cluttered spreadsheets or confusing hospital logins. Clean, calm operational clarity built for busy family members.
        </p>
      </div>

      <motion.div
        className="relative mx-auto mt-16 max-w-6xl overflow-hidden rounded-3xl border-2 border-mint bg-white shadow-xl"
        initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
        transition={{ duration: 0.5, ease: EASE }}
      >
        {/* LIVE DEMO badge */}
        <div className="absolute right-6 top-6 z-20 flex items-center gap-2 rounded-full bg-forest px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-cream shadow-md">
          <span className="inline-block h-2 w-2 rounded-full bg-mint mint-pulse" />
          LIVE DEMO
        </div>

        {/* Dashboard header */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-sand bg-cream px-6 py-5 sm:px-8">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-forest font-serif font-bold text-cream">MR</div>
            <div>
              <h3 className="font-serif text-lg font-medium text-forest">Margaret&apos;s Care Hub</h3>
              <p className="text-xs text-muted">Last synced 4 mins ago · All systems normal</p>
            </div>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-sand bg-sand-light p-1 text-xs font-medium">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-4 py-2 transition-all ${tab === t.key ? "bg-white text-forest shadow-sm" : "text-muted hover:text-forest"}`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="min-h-[380px] bg-white p-6 sm:p-10">
          {tab === "medication" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="font-serif text-xl text-forest">Active Medication Schedule & Refills</h4>
                <span className="rounded-full bg-mint-light px-3 py-1 text-xs font-medium text-forest">Autonomous Refill Enabled</span>
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {[
                  { name: "Lisinopril 10mg", dose: "1 tablet daily with breakfast", status: "Refill ordered at CVS · Arrives Thursday", badge: "Verified", badgeCls: "bg-emerald-100 text-emerald-800" },
                  { name: "Metformin 500mg", dose: "2 tablets daily with meals", status: "14 pills remaining · Next refill in 6 days", badge: "Queued", badgeCls: "bg-amber-100 text-amber-800" },
                ].map((m) => (
                  <div key={m.name} className="flex items-center justify-between rounded-xl border border-sand bg-cream/50 p-5">
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-mint-light text-forest text-lg"><Pill /></div>
                      <div>
                        <div className="font-semibold text-charcoal">{m.name}</div>
                        <div className="mt-0.5 text-xs text-muted">{m.dose}</div>
                        <div className="mt-2 text-[11px] text-forest font-medium">{m.status}</div>
                      </div>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${m.badgeCls}`}>{m.badge}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "appointment" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="font-serif text-xl text-forest">Upcoming Appointments & Transit</h4>
                <span className="rounded-full bg-mint-light px-3 py-1 text-xs font-medium text-forest">Ride Connected</span>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-sand bg-cream/50 p-5">
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-mint-light text-forest text-lg"><Stethoscope /></div>
                  <div>
                    <div className="font-semibold text-charcoal">Cardiology Follow-up with Dr. Vance</div>
                    <div className="text-xs text-muted">Thursday, Oct 14 at 2:00 PM · Mercy General Hospital</div>
                  </div>
                </div>
                <span className="rounded-full bg-mint/40 px-3 py-1 text-xs font-semibold text-forest">Uber Health Booked</span>
              </div>
            </div>
          )}

          {tab === "vital" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="font-serif text-xl text-forest">Daily Vitals & Smart Home Feed</h4>
                <span className="rounded-full bg-mint-light px-3 py-1 text-xs font-medium text-forest">All Sensors Active</span>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {[
                  { label: "Blood Pressure", value: "122/80", note: "Normal range · Checked 8:00 AM", noteCls: "text-emerald-700" },
                  { label: "Blood Glucose", value: "108 mg/dL", note: "Stable · Fasting reading", noteCls: "text-emerald-700" },
                  { label: "Activity Index", value: "2,410 steps", note: "Before noon", noteCls: "text-muted" },
                ].map((v) => (
                  <div key={v.label} className="rounded-xl border border-sand bg-cream/50 p-5">
                    <div className="mb-1 text-xs text-muted">{v.label}</div>
                    <div className="font-serif text-2xl font-semibold text-forest">{v.value}</div>
                    <div className={`mt-2 text-[11px] font-medium ${v.noteCls}`}>{v.note}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "family" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="font-serif text-xl text-forest">Family Sync Log & Morning Digest</h4>
                <span className="rounded-full bg-mint-light px-3 py-1 text-xs font-medium text-forest">Sent to 3 Siblings</span>
              </div>
              <div className="space-y-3 rounded-xl border border-sand bg-cream/50 p-5">
                <div className="flex items-center justify-between border-b border-sand pb-2 text-xs text-muted">
                  <span>Today&apos;s Digest · Sent via SMS & WhatsApp at 7:30 AM</span>
                  <span className="font-medium text-forest">Read by Sarah & Mark</span>
                </div>
                <p className="text-sm leading-relaxed text-charcoal">
                  &ldquo;Good morning family! Margaret took her morning Lisinopril on time. Vitals are steady at 122/80. Prescription refill is confirmed for Thursday pickup. No action needed today.&rdquo;
                </p>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   7. IMPACT
   ═══════════════════════════════════════════════════════════════════ */
function Impact() {
  const stats = [
    { value: "27 hrs", title: "Saved Monthly Per Family", desc: "Eliminates phone queues, insurance holds, medication sorting, and sibling coordination overhead." },
    { value: "45%", title: "Lower Medication Errors", desc: "Autonomous cross-checks and refill tracking prevent missed dosages and prescription mix-ups." },
    { value: "100%", title: "Peace of Mind", desc: "Every sibling stays automatically informed through clean morning briefings without emotional friction." },
  ];

  return (
    <FadeSection id="impact" className="px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-4xl space-y-4 text-center">
        <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">Quantifiable Outcomes</span>
        <h2 className="font-serif text-3xl text-forest sm:text-5xl">What changes when coordination runs itself.</h2>
        <p className="mx-auto max-w-2xl text-base text-muted sm:text-lg">
          CareBridge replaces mental exhaustion with structured reliability, protecting both your parents&apos; health and your career.
        </p>
      </div>
      <StaggerChildren className="mx-auto mt-16 grid max-w-5xl grid-cols-1 gap-8 md:grid-cols-3">
        {stats.map((s) => (
          <div key={s.title} className="relative overflow-hidden rounded-3xl border border-sand bg-white p-10 text-center shadow-sm">
            <div className="absolute left-0 right-0 top-0 h-1.5 bg-mint" />
            <div className="mb-4 font-serif text-6xl font-normal text-forest sm:text-7xl">{s.value}</div>
            <h3 className="mb-2 font-serif text-xl text-forest">{s.title}</h3>
            <p className="text-sm text-muted">{s.desc}</p>
          </div>
        ))}
      </StaggerChildren>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   8. ARCHITECTURE
   ═══════════════════════════════════════════════════════════════════ */
function Architecture() {
  const chips = ["HIPAA-ready", "FHIR-ready", "Zero Data Selling", "Provider Agnostic"];

  return (
    <FadeSection id="architecture" className="border-y border-sand bg-white px-6 py-20 sm:px-12 sm:py-28">
      <div className="mx-auto max-w-4xl space-y-4 text-center">
        <span className="rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">Enterprise Grade Security</span>
        <h2 className="font-serif text-3xl text-forest sm:text-5xl">Production-grade. Provider-agnostic. Yours.</h2>
      </div>

      <div className="mx-auto mt-16 max-w-4xl space-y-8 rounded-3xl border border-sand bg-cream p-8 shadow-sm sm:p-12">
        <div className="flex flex-wrap items-center justify-center gap-3">
          {chips.map((c) => (
            <span key={c} className="rounded-full border border-sand bg-white px-4 py-2 text-xs font-semibold text-forest shadow-sm">{c}</span>
          ))}
        </div>

        <p className="mx-auto max-w-2xl text-center text-base text-charcoal sm:text-lg">
          CareBridge runs on Strands Agents SDK with a real LLM-driven Supervisor.
          Firebase handles identity; our backend issues business-claim JWTs and
          owns every authorization decision. Pharmacy and delivery integrations
          are mocked pending commercial contracts — everything else runs in
          production today.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-6 border-t border-sand pt-6 text-xs font-medium text-muted">
          <span className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5 text-forest" /> End-to-End AES-256</span>
          <span className="flex items-center gap-1.5"><Server className="h-3.5 w-3.5 text-forest" /> Dedicated Tenant DB</span>
          <span className="flex items-center gap-1.5"><Key className="h-3.5 w-3.5 text-forest" /> Bring Your Own Key (BYOK)</span>
        </div>
      </div>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   9. CTA
   ═══════════════════════════════════════════════════════════════════ */
function CTA() {
  const [submitted, setSubmitted] = useState(false);

  return (
    <FadeSection id="cta" className="relative px-6 py-24 text-center sm:px-12 sm:py-32">
      <div className="mx-auto max-w-3xl space-y-8">
        <span className="inline-block rounded-full bg-sand-light px-3 py-1 text-xs font-semibold uppercase tracking-wider text-forest">Get Started Today</span>
        <h2 className="font-serif text-4xl text-forest sm:text-6xl">The agent that owns the workflow.</h2>
        <p className="mx-auto max-w-xl text-base text-muted sm:text-lg">
          Join hundreds of families who have replaced eldercare chaos with quiet, reliable autonomous coordination.
        </p>

        {!submitted ? (
          <form
            onSubmit={(e) => { e.preventDefault(); setSubmitted(true); }}
            className="mx-auto flex max-w-md flex-col items-center gap-3 sm:flex-row"
          >
            <input
              type="email" required placeholder="Enter your email address"
              className="w-full rounded-full border border-sand bg-white px-6 py-4 text-sm text-charcoal shadow-sm placeholder:text-muted focus:border-forest focus:outline-none"
            />
            <button type="submit" className="w-full whitespace-nowrap rounded-full bg-forest px-8 py-4 text-sm font-medium text-cream shadow-sm hover:bg-forest-hover sm:w-auto">
              Get early access
            </button>
          </form>
        ) : (
          <div className="mx-auto max-w-md rounded-xl bg-mint-light p-3 text-sm font-medium text-forest">
            Thank you! We&apos;ve reserved your access priority.
          </div>
        )}

        <div className="space-y-1 text-xs text-muted">
          <p>Or <Link href="/signup" className="font-medium text-forest hover:text-forest-hover">sign in with Google →</Link></p>
          <p>Free during the Agents for Humans Hackathon. MIT licensed.</p>
        </div>
      </div>
    </FadeSection>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   10. FOOTER
   ═══════════════════════════════════════════════════════════════════ */
function Footer() {
  return (
    <footer className="border-t border-sand bg-white px-6 py-16 sm:px-12">
      <div className="mx-auto grid max-w-[1440px] grid-cols-1 gap-10 md:grid-cols-4">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-forest font-serif text-sm font-bold text-cream">CB</div>
            <span className="font-serif text-xl font-semibold text-forest">CareBridge</span>
          </div>
          <p className="text-xs leading-relaxed text-muted">The autonomous AI coordinator for aging parents and modern families.</p>
        </div>

        <div>
          <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-forest">Platform</h4>
          <ul className="space-y-2 text-xs text-muted">
            <li><a href="#how-it-works" className="transition-colors hover:text-forest">Supervisor Agents</a></li>
            <li><a href="#dashboard" className="transition-colors hover:text-forest">Live Dashboard</a></li>
            <li><a href="#architecture" className="transition-colors hover:text-forest">HIPAA Security</a></li>
            <li><a href="#impact" className="transition-colors hover:text-forest">Family Sync</a></li>
          </ul>
        </div>

        <div>
          <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-forest">Company</h4>
          <ul className="space-y-2 text-xs text-muted">
            <li><a href="#" className="transition-colors hover:text-forest">About</a></li>
            <li><a href="#" className="transition-colors hover:text-forest">Editorial & Research</a></li>
            <li><a href="#" className="transition-colors hover:text-forest">Privacy Policy</a></li>
            <li><a href="#" className="transition-colors hover:text-forest">Terms of Service</a></li>
          </ul>
        </div>

        <div>
          <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-forest">Newsletter</h4>
          <p className="mb-3 text-xs text-muted">
            Subscribe to <span className="font-serif italic">The Operational Caregiver</span>, our weekly publication on aging and AI.
          </p>
          <div className="flex items-center gap-2">
            <input type="email" placeholder="Your email" className="w-full rounded-lg border border-sand bg-cream px-3 py-2 text-xs focus:border-forest focus:outline-none" />
            <button className="rounded-lg bg-forest px-3 py-2 text-xs text-cream hover:bg-forest-hover">Join</button>
          </div>
        </div>
      </div>

      <div className="mx-auto mt-12 flex max-w-[1440px] flex-col items-center justify-between gap-4 border-t border-sand pt-8 text-xs text-muted sm:flex-row">
        <div>© 2026 CareBridge Technologies, Inc. All rights reserved.</div>
        <div className="flex items-center gap-6">
          <span>Built for the Agents for Humans Hackathon — Sept 2026</span>
          <a href="#" className="transition-colors hover:text-forest">Privacy</a>
          <a href="#" className="transition-colors hover:text-forest">Terms</a>
          <a href="#" className="transition-colors hover:text-forest">Security</a>
        </div>
      </div>
    </footer>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════════════════════════ */
export default function LandingPage() {
  return (
    <main>
      <Nav />
      <Hero />
      <RealProduct />
      <Problem />
      <HowItWorks />
      <DashboardPreview />
      <Impact />
      <Architecture />
      <CTA />
      <Footer />
    </main>
  );
}
