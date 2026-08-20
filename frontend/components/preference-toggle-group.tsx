"use client";

import { Moon, RouteOff, ShieldCheck } from "lucide-react";

import { preferenceOptions } from "@/lib/constants";
import type { Preferences } from "@/lib/types";
import { cn } from "@/lib/utils";

const icons = {
  avoid_highways: RouteOff,
  avoid_night_risk: Moon,
  prefer_safest: ShieldCheck
};

type PreferenceToggleGroupProps = {
  value: Preferences;
  onChange: (value: Preferences) => void;
};

export function PreferenceToggleGroup({ value, onChange }: PreferenceToggleGroupProps) {
  return (
    <div>
      <label className="text-sm font-medium text-neutral-950">Preferences</label>
      <div className="mt-3 space-y-2">
        {preferenceOptions.map((option) => {
          const Icon = icons[option.key];
          const checked = value[option.key];
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => onChange({ ...value, [option.key]: !checked })}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition duration-200 ease-out hover:border-neutral-300 focus:outline-none focus:ring-2 focus:ring-neutral-950 focus:ring-offset-2",
                checked ? "border-neutral-950 bg-neutral-950 text-white" : "border-border bg-white text-neutral-950"
              )}
              aria-pressed={checked}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border",
                  checked ? "border-white bg-white text-neutral-950" : "border-neutral-300 bg-white text-neutral-600"
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
              <span>
                <span className="block text-sm font-semibold">{option.label}</span>
                <span className={cn("mt-1 block text-xs leading-5", checked ? "text-neutral-200" : "text-neutral-500")}>
                  {option.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
