"use client";

import { Baby, Gauge, ShieldCheck, UserRound } from "lucide-react";

import { driverProfileOptions } from "@/lib/constants";
import type { DriverProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const icons = {
  new_driver: UserRound,
  normal_driver: Gauge,
  cautious_driver: ShieldCheck,
  parent_mode: Baby
};

type DriverProfileSelectorProps = {
  value: DriverProfile;
  onChange: (value: DriverProfile) => void;
};

export function DriverProfileSelector({ value, onChange }: DriverProfileSelectorProps) {
  return (
    <div>
      <label className="text-sm font-medium text-neutral-950">Driver profile</label>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {driverProfileOptions.map((option) => {
          const Icon = icons[option.value];
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className={cn(
                "rounded-lg border p-3 text-left transition duration-200 ease-out hover:-translate-y-px focus:outline-none focus:ring-2 focus:ring-neutral-950 focus:ring-offset-2",
                selected ? "border-neutral-950 bg-neutral-950 text-white" : "border-border bg-white text-neutral-950"
              )}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="text-sm font-semibold">{option.label}</span>
              </div>
              <p className={cn("mt-2 text-xs leading-5", selected ? "text-neutral-200" : "text-neutral-500")}>
                {option.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
