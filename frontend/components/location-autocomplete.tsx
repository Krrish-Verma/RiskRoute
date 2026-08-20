"use client";

import { Loader2, LocateFixed } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { searchLocations, toApiError } from "@/lib/api";
import type { LocationSuggestion } from "@/lib/types";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;
const DALLAS_LAUNCH_BOUNDS = {
  minLat: 32.6,
  maxLat: 33.15,
  minLng: -97.05,
  maxLng: -96.4
} as const;

export type LocationFieldValue = {
  display: string;
  submitValue: string;
};

type LocationAutocompleteProps = {
  id: string;
  label: string;
  value: LocationFieldValue;
  onChange: (value: LocationFieldValue) => void;
  placeholder: string;
  icon: ReactNode;
  disabled?: boolean;
  allowCurrentLocation?: boolean;
};

type SearchState = "idle" | "loading" | "success" | "empty" | "error";
type GeolocationState = "idle" | "locating" | "selected" | "error";

function coordinatesFor(suggestion: LocationSuggestion) {
  return `${suggestion.lat.toFixed(6)},${suggestion.lng.toFixed(6)}`;
}

function isInsideLaunchArea(lat: number, lng: number) {
  return lat >= DALLAS_LAUNCH_BOUNDS.minLat
    && lat <= DALLAS_LAUNCH_BOUNDS.maxLat
    && lng >= DALLAS_LAUNCH_BOUNDS.minLng
    && lng <= DALLAS_LAUNCH_BOUNDS.maxLng;
}

function geolocationErrorMessage(error: GeolocationPositionError) {
  if (error.code === error.PERMISSION_DENIED) {
    return "Location permission was denied. Enable it in your browser or enter an address.";
  }
  if (error.code === error.POSITION_UNAVAILABLE) {
    return "Your current location is unavailable. Check device location services and try again.";
  }
  if (error.code === error.TIMEOUT) {
    return "Current location timed out. Try again or enter an address.";
  }
  return "RiskRoute could not read your current location. Try again or enter an address.";
}

export function LocationAutocomplete({
  id,
  label,
  value,
  onChange,
  placeholder,
  icon,
  disabled = false,
  allowCurrentLocation = false
}: LocationAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  const [searchState, setSearchState] = useState<SearchState>("idle");
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [searchRetryable, setSearchRetryable] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [retryCount, setRetryCount] = useState(0);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const [geolocationState, setGeolocationState] = useState<GeolocationState>("idle");
  const [geolocationMessage, setGeolocationMessage] = useState<string | null>(null);
  const focusedRef = useRef(false);
  const geolocationAttemptRef = useRef(0);

  const listboxId = `${id}-suggestions`;
  const searchStatusId = `${id}-search-status`;
  const geolocationStatusId = `${id}-geolocation-status`;
  const query = value.display.trim();
  const isUnresolvedText = value.submitValue === value.display;

  useEffect(() => {
    if (disabled || !searchEnabled || query.length < 3 || !isUnresolvedText) {
      setSuggestions([]);
      setSearchState("idle");
      setSearchRetryable(false);
      if (isUnresolvedText) setSearchMessage(null);
      setOpen(false);
      setActiveIndex(-1);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearchState("loading");
      setSearchMessage("Searching Dallas-area locations…");
      try {
        const result = await searchLocations(query, { limit: 5, signal: controller.signal });
        if (controller.signal.aborted) return;
        setSuggestions(result.data.suggestions);
        setSearchRetryable(false);
        setActiveIndex(-1);
        if (result.data.suggestions.length === 0) {
          setSearchState("empty");
          setSearchMessage("No Dallas-area matches found. Try a street address or nearby landmark.");
        } else {
          setSearchState("success");
          setSearchMessage(`${result.data.suggestions.length} Dallas-area suggestion${result.data.suggestions.length === 1 ? "" : "s"} available.`);
        }
        setOpen(focusedRef.current);
      } catch (error) {
        const apiError = toApiError(error);
        if (apiError.code === "request_aborted") return;
        setSuggestions([]);
        setActiveIndex(-1);
        setSearchState("error");
        setSearchRetryable(apiError.retryable);
        setSearchMessage(apiError.requestId
          ? `${apiError.message} Request ${apiError.requestId}.`
          : apiError.message);
        setOpen(focusedRef.current);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [disabled, isUnresolvedText, query, retryCount, searchEnabled]);

  useEffect(() => () => {
    geolocationAttemptRef.current += 1;
  }, []);

  function handleTextChange(nextDisplay: string) {
    onChange({ display: nextDisplay, submitValue: nextDisplay });
    setSearchEnabled(nextDisplay.trim().length >= 3);
    setSuggestions([]);
    setSearchState("idle");
    setSearchMessage(null);
    setSearchRetryable(false);
    setActiveIndex(-1);
    setOpen(nextDisplay.trim().length >= 3);
    setGeolocationState("idle");
    setGeolocationMessage(null);
  }

  function selectSuggestion(suggestion: LocationSuggestion) {
    onChange({ display: suggestion.name, submitValue: coordinatesFor(suggestion) });
    setSearchEnabled(false);
    setOpen(false);
    setActiveIndex(-1);
    setSearchState("idle");
    setSearchRetryable(false);
    setSearchMessage(`${suggestion.name} selected.`);
    setGeolocationState("idle");
    setGeolocationMessage(null);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && suggestions.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => {
        if (event.key === "ArrowDown") return current < suggestions.length - 1 ? current + 1 : 0;
        return current > 0 ? current - 1 : suggestions.length - 1;
      });
      return;
    }
    if (event.key === "Enter" && open && activeIndex >= 0) {
      event.preventDefault();
      selectSuggestion(suggestions[activeIndex]);
    }
  }

  function useCurrentLocation() {
    const attempt = geolocationAttemptRef.current + 1;
    geolocationAttemptRef.current = attempt;
    setGeolocationState("locating");
    setGeolocationMessage("Waiting for browser location permission…");

    if (!("geolocation" in navigator)) {
      setGeolocationState("error");
      setGeolocationMessage("Current location is unavailable in this browser. Enter an address instead.");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (geolocationAttemptRef.current !== attempt) return;
        const { latitude, longitude } = position.coords;
        if (!isInsideLaunchArea(latitude, longitude)) {
          setGeolocationState("error");
          setGeolocationMessage("Your current location is outside the Dallas / North Dallas launch area.");
          return;
        }
        const submitValue = `${latitude.toFixed(6)},${longitude.toFixed(6)}`;
        onChange({
          display: `Current location (${latitude.toFixed(5)}, ${longitude.toFixed(5)})`,
          submitValue
        });
        setSearchEnabled(false);
        setOpen(false);
        setSuggestions([]);
        setSearchState("idle");
        setSearchRetryable(false);
        setSearchMessage(null);
        setGeolocationState("selected");
        setGeolocationMessage("Current location selected within Dallas-area coverage.");
      },
      (error) => {
        if (geolocationAttemptRef.current !== attempt) return;
        setGeolocationState("error");
        setGeolocationMessage(geolocationErrorMessage(error));
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 }
    );
  }

  const showResults = open && query.length >= 3 && isUnresolvedText;
  const activeDescendant = showResults && activeIndex >= 0 ? `${id}-suggestion-${activeIndex}` : undefined;

  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-neutral-950">
        {label}
      </label>
      <div className="relative mt-2">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-white px-3 py-2 focus-within:ring-2 focus-within:ring-neutral-950">
          {icon}
          <input
            id={id}
            value={value.display}
            onChange={(event) => handleTextChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              focusedRef.current = true;
              if (query.length >= 3 && isUnresolvedText) {
                setSearchEnabled(true);
                setOpen(true);
              }
            }}
            onBlur={() => {
              focusedRef.current = false;
              setOpen(false);
            }}
            className="w-full border-0 bg-transparent text-sm outline-none disabled:cursor-not-allowed"
            placeholder={placeholder}
            maxLength={200}
            required
            disabled={disabled}
            autoComplete="off"
            spellCheck={false}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={showResults}
            aria-controls={listboxId}
            aria-activedescendant={activeDescendant}
            aria-describedby={searchStatusId}
            aria-busy={searchState === "loading"}
          />
          {searchState === "loading" ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-neutral-400" aria-hidden="true" /> : null}
        </div>

        {showResults ? (
          <div className="absolute z-[1000] mt-2 w-full overflow-hidden rounded-xl border border-border bg-white shadow-lg">
            {suggestions.length > 0 ? (
              <ul id={listboxId} role="listbox" aria-label={`${label} suggestions`} className="max-h-64 overflow-y-auto py-1">
                {suggestions.map((suggestion, index) => (
                  <li
                    key={`${suggestion.name}-${suggestion.lat}-${suggestion.lng}`}
                    id={`${id}-suggestion-${index}`}
                    role="option"
                    aria-selected={index === activeIndex}
                    className={cn(
                      "cursor-pointer px-3 py-2.5 transition-colors",
                      index === activeIndex ? "bg-neutral-100" : "hover:bg-neutral-50"
                    )}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseMove={() => setActiveIndex(index)}
                    onClick={() => selectSuggestion(suggestion)}
                  >
                    <span className="block text-sm font-medium text-neutral-950">{suggestion.name}</span>
                    <span className="mt-0.5 block text-xs text-neutral-500">
                      {suggestion.lat.toFixed(5)}, {suggestion.lng.toFixed(5)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : searchState === "error" ? (
              <div className="flex items-start justify-between gap-3 px-3 py-3">
                <p className="text-xs leading-5 text-red-700">{searchMessage}</p>
                {searchRetryable ? (
                  <button
                    type="button"
                    className="shrink-0 text-xs font-semibold text-neutral-950 underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-neutral-950"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => setRetryCount((count) => count + 1)}
                  >
                    Retry
                  </button>
                ) : null}
              </div>
            ) : searchState === "empty" ? (
              <p className="px-3 py-3 text-xs leading-5 text-neutral-600">{searchMessage}</p>
            ) : (
              <p className="px-3 py-3 text-xs text-neutral-500">Searching Dallas-area locations…</p>
            )}
          </div>
        ) : null}
      </div>

      <p id={searchStatusId} className={cn(
        "mt-1.5 text-xs leading-5",
        searchState === "error" ? "text-red-700" : "text-neutral-500",
        searchState === "idle" && !searchMessage ? "sr-only" : ""
      )} aria-live="polite">
        {searchMessage || "Type at least 3 characters to search Dallas and North Dallas."}
      </p>

      {allowCurrentLocation ? (
        <div className="mt-2">
          <button
            type="button"
            onClick={useCurrentLocation}
            disabled={disabled || geolocationState === "locating"}
            className="inline-flex items-center gap-1.5 rounded-md text-xs font-semibold text-neutral-700 transition-colors hover:text-neutral-950 focus:outline-none focus:ring-2 focus:ring-neutral-950 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            aria-describedby={geolocationStatusId}
          >
            {geolocationState === "locating"
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              : <LocateFixed className="h-3.5 w-3.5" aria-hidden="true" />}
            {geolocationState === "locating" ? "Locating…" : "Use current location"}
          </button>
          <p
            id={geolocationStatusId}
            className={cn(
              "mt-1 text-xs leading-5",
              geolocationState === "error" ? "text-red-700" : geolocationState === "selected" ? "text-green-700" : "text-neutral-500",
              geolocationState === "idle" ? "sr-only" : ""
            )}
            role={geolocationState === "error" ? "alert" : "status"}
          >
            {geolocationMessage || "Current location has not been requested."}
          </p>
        </div>
      ) : null}
    </div>
  );
}
