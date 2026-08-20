import { RouteCard } from "@/components/route-card";
import type { RouteAnalysis } from "@/lib/types";

type RouteComparisonProps = {
  routes: RouteAnalysis[];
  selectedRouteId?: string | null;
  onSelectRoute?: (routeId: string) => void;
  emptyTitle?: string;
  emptyDescription?: string;
};

export function RouteComparison({
  routes,
  selectedRouteId,
  onSelectRoute,
  emptyTitle = "No route analysis yet",
  emptyDescription = "Enter a route to compare ETA, crash exposure, and risk tradeoffs."
}: RouteComparisonProps) {
  if (!routes.length) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center">
        <p className="text-sm font-medium text-neutral-950">{emptyTitle}</p>
        <p className="mt-2 text-sm text-neutral-500">{emptyDescription}</p>
      </div>
    );
  }

  const cards = (
    <div className="grid gap-4 xl:grid-cols-3">
      {routes.map((route) => (
        <RouteCard
          key={route.route_id}
          route={route}
          selected={route.route_id === selectedRouteId}
          onSelect={onSelectRoute ? () => onSelectRoute(route.route_id) : undefined}
        />
      ))}
    </div>
  );

  if (!onSelectRoute) return cards;

  return (
    <fieldset>
      <legend className="mb-3 text-sm font-semibold text-neutral-950">Choose a route for your report</legend>
      {cards}
    </fieldset>
  );
}
