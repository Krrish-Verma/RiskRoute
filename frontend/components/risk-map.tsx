"use client";

import L from "leaflet";
import { MapPinned } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";

import type { CrashPoint, Hotspot, RouteAnalysis } from "@/lib/types";
import { cn, routeStroke } from "@/lib/utils";

type MapBounds = [[number, number], [number, number]];

type RiskMapProps = {
  routes?: RouteAnalysis[];
  hotspots?: Hotspot[];
  selectedRouteId?: string | null;
  onSelectRoute?: (routeId: string) => void;
  className?: string;
};

const DALLAS_CENTER: [number, number] = [32.8998, -96.789];

function boundsFor(routes: RouteAnalysis[], hotspots: Hotspot[]): MapBounds | null {
  const coords = [
    ...routes.flatMap((route) => route.geometry.coordinates),
    ...hotspots.map((hotspot) => [hotspot.lng, hotspot.lat])
  ].filter((coord) => coord.length >= 2 && Number.isFinite(coord[0]) && Number.isFinite(coord[1]));

  if (!coords.length) return null;
  return [
    [Math.min(...coords.map((coord) => coord[1])), Math.min(...coords.map((coord) => coord[0]))],
    [Math.max(...coords.map((coord) => coord[1])), Math.max(...coords.map((coord) => coord[0]))]
  ];
}

function createIcon(color: string, size = 12) {
  return L.divIcon({
    className: "",
    html: `<span aria-hidden="true" style="display:inline-block;width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2px solid white;box-shadow:0 0 0 2px rgba(0,0,0,0.12);"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2]
  });
}

function MapViewport({ bounds }: { bounds: MapBounds | null }) {
  const map = useMap();

  useEffect(() => {
    map.invalidateSize();
    if (bounds) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 });
    } else {
      map.setView(DALLAS_CENTER, 10);
    }
  }, [bounds, map]);

  return null;
}

function uniqueCrashPoints(routes: RouteAnalysis[], selectedRouteId?: string | null) {
  const visibleRoutes = selectedRouteId
    ? routes.filter((route) => route.route_id === selectedRouteId)
    : routes;
  const points = new Map<number, CrashPoint>();
  visibleRoutes.forEach((route) => route.crash_points.forEach((point) => points.set(point.id, point)));
  return Array.from(points.values()).slice(0, 50);
}

export function RiskMap({ routes = [], hotspots = [], selectedRouteId, onSelectRoute, className = "" }: RiskMapProps) {
  const bounds = useMemo(() => boundsFor(routes, hotspots), [routes, hotspots]);
  const crashPoints = useMemo(() => uniqueCrashPoints(routes, selectedRouteId), [routes, selectedRouteId]);
  const [tileError, setTileError] = useState(false);
  const orderedRoutes = useMemo(
    () => [...routes].sort((a, b) => Number(a.route_id === selectedRouteId) - Number(b.route_id === selectedRouteId)),
    [routes, selectedRouteId]
  );

  return (
    <div className={cn("relative min-h-[360px] overflow-hidden rounded-lg border border-border bg-surface", className)} role="region" aria-label="Dallas route risk map">
      <div className="absolute left-4 top-4 z-[1000] inline-flex items-center gap-2 rounded-full border border-border bg-white px-3 py-1.5 text-xs font-medium text-neutral-600 shadow-card">
        <MapPinned className="h-3.5 w-3.5" aria-hidden="true" />
        Dallas / North Dallas
      </div>
      {tileError ? (
        <div className="absolute right-4 top-4 z-[1000] rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-xs text-neutral-700" role="status">
          Base map tiles are temporarily unavailable. Route data remains visible.
        </div>
      ) : null}
      <MapContainer center={DALLAS_CENTER} zoom={10} scrollWheelZoom className="h-[420px] w-full">
        <MapViewport bounds={bounds} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          eventHandlers={{ tileerror: () => setTileError(true), load: () => setTileError(false) }}
        />
        {orderedRoutes.map((route) => {
          const selected = route.route_id === selectedRouteId;
          return (
            <Polyline
              key={route.route_id}
              positions={route.geometry.coordinates.map((coord) => [coord[1], coord[0]])}
              pathOptions={{
                color: routeStroke(route),
                weight: selected ? 8 : route.recommended ? 5 : 4,
                opacity: selected ? 1 : selectedRouteId ? 0.42 : 0.78
              }}
              eventHandlers={onSelectRoute ? { click: () => onSelectRoute(route.route_id) } : undefined}
            >
              <Popup>
                <div>
                  <strong>{route.label}</strong>
                  <br />Risk index {route.risk_score.toFixed(1)} · {route.risk_level}
                  <br />{route.confidence ? `${route.confidence} confidence` : "Confidence not reported"}
                </div>
              </Popup>
            </Polyline>
          );
        })}
        {crashPoints.map((point) => (
          <Marker key={point.id} position={[point.lat, point.lng]} icon={createIcon("#F97316")}>
            <Popup>
              <div>
                <strong>{point.severity}</strong>
                <br />Severity score: {point.severity_score}
                {point.street_name ? <><br />{point.street_name}</> : null}
                <br /><span>Historical crash record</span>
              </div>
            </Popup>
          </Marker>
        ))}
        {hotspots.map((hotspot) => (
          <Marker key={`${hotspot.lat}-${hotspot.lng}`} position={[hotspot.lat, hotspot.lng]} icon={createIcon("#DC2626", 14)}>
            <Popup>
              <div>
                <strong>{hotspot.city || "Dallas area"}{hotspot.state ? `, ${hotspot.state}` : ""}</strong>
                <br />Relative risk index: {hotspot.risk_score.toFixed(1)}
                <br />Historical crashes: {hotspot.crash_count}
                <br />Severity sum: {hotspot.severity_score.toFixed(1)}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {(routes.length || hotspots.length) ? (
        <div className="absolute bottom-6 left-4 z-[1000] max-w-[calc(100%-2rem)] rounded-lg border border-border bg-white/95 p-3 text-xs text-neutral-700 shadow-card backdrop-blur">
          <p className="font-semibold text-neutral-950">Map legend</p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
            {routes.map((route) => (
              <span key={route.route_id} className="inline-flex items-center gap-1.5">
                <span className="h-1 w-5 rounded-full" style={{ backgroundColor: routeStroke(route) }} />
                {route.label}{route.route_id === selectedRouteId ? " (selected)" : ""}
              </span>
            ))}
            {crashPoints.length ? <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-risk-high" /> Crash record</span> : null}
            {hotspots.length ? <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-risk-severe" /> Hotspot cell</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
