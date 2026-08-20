import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: string;
  description: string;
  icon?: ReactNode;
};

export function StatCard({ label, value, description, icon }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-white p-5 shadow-card">
      <div className="mb-6 flex items-center justify-between gap-4">
        <p className="text-sm font-medium text-neutral-500">{label}</p>
        {icon ? <div className="text-neutral-950">{icon}</div> : null}
      </div>
      <p className="text-3xl font-semibold text-neutral-950">{value}</p>
      <p className="mt-2 text-sm leading-6 text-neutral-500">{description}</p>
    </div>
  );
}
