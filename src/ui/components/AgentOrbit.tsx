"use client";

import React, { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { Pill, CalendarDays, Truck, MessageSquare, Brain } from "lucide-react";

const SPECIALISTS = [
  { name: "Medication", icon: Pill, color: "bg-blue-500", angle: 0 },
  { name: "Appointment", icon: CalendarDays, color: "bg-cyan-500", angle: 90 },
  { name: "Logistics", icon: Truck, color: "bg-orange-500", angle: 180 },
  { name: "Communication", icon: MessageSquare, color: "bg-pink-500", angle: 270 },
];

/* Warm editorial motion — long settle, never bouncy */
const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

export default function AgentOrbit() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <div ref={ref} className="relative mx-auto flex h-80 w-80 items-center justify-center md:h-96 md:w-96">
      {/* Orbit ring */}
      <div className="absolute h-64 w-64 rounded-full border-2 border-dashed border-stone-300 md:h-72 md:w-72" />

      {/* Supervisor center */}
      <motion.div
        className="relative z-10 flex h-20 w-20 items-center justify-center rounded-full bg-forest-600 text-white shadow-lg"
        animate={inView ? { scale: [1, 1.04, 1] } : {}}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        aria-label="Supervisor Agent"
      >
        <Brain className="h-8 w-8" aria-hidden="true" />
      </motion.div>

      {/* Specialists */}
      {SPECIALISTS.map((spec, i) => {
        const radius = 128; // half of 256 (orbit diameter)
        const rad = (spec.angle * Math.PI) / 180;
        const x = Math.cos(rad) * radius;
        const y = Math.sin(rad) * radius;

        return (
          <motion.div
            key={spec.name}
            className="absolute flex flex-col items-center gap-1"
            initial={{ opacity: 0, scale: 0.5 }}
            animate={inView ? { opacity: 1, scale: 1, x, y } : {}}
            transition={{ delay: 0.3 + i * 0.2, duration: 0.5, ease: EASE }}
          >
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-full ${spec.color} text-white shadow-md`}
            >
              <spec.icon className="h-5 w-5" aria-hidden="true" />
            </div>
            <span className="font-serif text-xs font-medium text-stone-700">{spec.name}</span>
          </motion.div>
        );
      })}
    </div>
  );
}
