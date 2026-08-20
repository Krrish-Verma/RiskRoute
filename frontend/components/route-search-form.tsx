"use client";

import { ArrowRight, Loader2, MapPin, Navigation } from "lucide-react";
import { FormEvent, useState } from "react";

import { DriverProfileSelector } from "@/components/driver-profile-selector";
import { LocationAutocomplete, type LocationFieldValue } from "@/components/location-autocomplete";
import { PreferenceToggleGroup } from "@/components/preference-toggle-group";
import { Button } from "@/components/ui/button";
import type { AnalyzeRouteRequest, DriverProfile, Preferences } from "@/lib/types";

type RouteSearchFormProps = {
  onSubmit: (payload: AnalyzeRouteRequest) => void;
  loading?: boolean;
};

export function RouteSearchForm({ onSubmit, loading = false }: RouteSearchFormProps) {
  const [origin, setOrigin] = useState<LocationFieldValue>({
    display: "Dallas City Hall, Dallas, TX",
    submitValue: "Dallas City Hall, Dallas, TX"
  });
  const [destination, setDestination] = useState<LocationFieldValue>({
    display: "Galleria Dallas, Dallas, TX",
    submitValue: "Galleria Dallas, Dallas, TX"
  });
  const [driverProfile, setDriverProfile] = useState<DriverProfile>("new_driver");
  const [departureTime, setDepartureTime] = useState("");
  const [preferences, setPreferences] = useState<Preferences>({
    avoid_highways: false,
    avoid_night_risk: true,
    prefer_safest: true
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      origin: origin.submitValue.trim(),
      destination: destination.submitValue.trim(),
      driver_profile: driverProfile,
      departure_time: departureTime ? new Date(departureTime).toISOString() : null,
      preferences
    });
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-white p-5 shadow-card">
      <div className="flex items-center gap-2 border-b border-border pb-4">
        <Navigation className="h-4 w-4 text-neutral-950" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-neutral-950">Analyze route</h2>
      </div>

      <div className="mt-5 space-y-4">
        <LocationAutocomplete
          id="origin"
          label="Origin"
          value={origin}
          onChange={setOrigin}
          placeholder="Start address or place"
          icon={<MapPin className="h-4 w-4 shrink-0 text-neutral-400" aria-hidden="true" />}
          disabled={loading}
          allowCurrentLocation
        />

        <LocationAutocomplete
          id="destination"
          label="Destination"
          value={destination}
          onChange={setDestination}
          placeholder="Destination address or place"
          icon={<ArrowRight className="h-4 w-4 shrink-0 text-neutral-400" aria-hidden="true" />}
          disabled={loading}
        />

        <div>
          <label htmlFor="departure_time" className="text-sm font-medium text-neutral-950">
            Departure time
          </label>
          <input
            id="departure_time"
            type="datetime-local"
            value={departureTime}
            onChange={(event) => setDepartureTime(event.target.value)}
            className="mt-2 w-full rounded-lg border border-border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-neutral-950"
          />
        </div>
      </div>

      <div className="mt-6">
        <DriverProfileSelector value={driverProfile} onChange={setDriverProfile} />
      </div>

      <div className="mt-6">
        <PreferenceToggleGroup value={preferences} onChange={setPreferences} />
      </div>

      <Button type="submit" className="mt-6 w-full py-3" disabled={loading}>
        {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Navigation className="h-4 w-4" aria-hidden="true" />}
        Analyze routes
      </Button>
    </form>
  );
}
