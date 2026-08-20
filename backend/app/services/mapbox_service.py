from __future__ import annotations

import asyncio
import hashlib
import math
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings
from app.errors import OutsideCoverageError, UpstreamServiceError
from app.models.schemas import Location, Preferences
from app.services.route_sampler import haversine_distance_meters


@dataclass
class RawRoute:
    route_id: str
    duration_seconds: float
    distance_meters: float
    geometry: dict


KNOWN_DALLAS_LOCATIONS = {
    "downtown dallas": Location(name="Downtown Dallas, Dallas, TX", lat=32.7767, lng=-96.7970),
    "dallas": Location(name="Dallas, TX", lat=32.7767, lng=-96.7970),
    "north dallas": Location(name="North Dallas, Dallas, TX", lat=32.9398, lng=-96.8039),
    "galleria dallas": Location(name="Galleria Dallas, Dallas, TX", lat=32.9304, lng=-96.8197),
    "addison": Location(name="Addison, TX", lat=32.9618, lng=-96.8292),
    "richardson": Location(name="Richardson, TX", lat=32.9483, lng=-96.7299),
    "plano": Location(name="Plano, TX", lat=33.0198, lng=-96.6989),
}


def _stable_offset(text: str, scale: float = 0.045) -> tuple[float, float]:
    digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
    lat_raw = int(digest[:8], 16) / 0xFFFFFFFF
    lng_raw = int(digest[8:16], 16) / 0xFFFFFFFF
    return (lat_raw - 0.5) * scale, (lng_raw - 0.5) * scale


class MapboxService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._circuit_lock = threading.Lock()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _before_request(self) -> None:
        with self._circuit_lock:
            remaining = self._circuit_open_until - time.monotonic()
        if remaining > 0:
            raise UpstreamServiceError(
                "The routing provider is temporarily unavailable. Retry shortly.",
                details={
                    "provider": "mapbox",
                    "reason": "circuit_open",
                    "retry_after_seconds": max(1, round(remaining)),
                },
            )

    def _record_success(self) -> None:
        with self._circuit_lock:
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0

    def _record_failure(self) -> None:
        with self._circuit_lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.settings.mapbox_circuit_failure_threshold:
                self._circuit_open_until = (
                    time.monotonic() + self.settings.mapbox_circuit_reset_seconds
                )

    async def _request(self, url: str, params: dict[str, str]) -> dict:
        self._before_request()
        last_error: Exception | None = None
        for attempt in range(self.settings.mapbox_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.settings.mapbox_timeout_seconds) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                if payload.get("code") not in (None, "Ok"):
                    raise ValueError(f"Mapbox response code {payload.get('code')}")
                self._record_success()
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500
                if attempt >= self.settings.mapbox_max_retries or not retryable:
                    break
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        self._record_failure()
        raise UpstreamServiceError(
            "The routing provider is unavailable. Retry shortly.",
            details={"provider": "mapbox", "reason": last_error.__class__.__name__ if last_error else "unknown"},
        ) from last_error

    def _demo_geocode(self, query: str) -> Location:
        normalized = query.casefold()
        for key in sorted(KNOWN_DALLAS_LOCATIONS, key=len, reverse=True):
            if key in normalized:
                return KNOWN_DALLAS_LOCATIONS[key]
        lat_offset, lng_offset = _stable_offset(query)
        return Location(name=f"{query} (demo)", lat=32.86 + lat_offset, lng=-96.79 + lng_offset)

    def _coordinate_location(self, query: str) -> Location | None:
        match = re.fullmatch(
            r"\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*",
            query,
        )
        if match is None:
            return None
        lat, lng = float(match.group(1)), float(match.group(2))
        if not math.isfinite(lat) or not math.isfinite(lng):
            return None
        if not self.settings.contains_location(lat, lng):
            raise OutsideCoverageError(
                f"RiskRoute currently covers {self.settings.launch_area_name} only.",
                details={"query": query, "launch_area": self.settings.launch_area_name},
            )
        return Location(name=f"Current location ({lat:.5f}, {lng:.5f})", lat=lat, lng=lng)

    def _feature_location(self, feature: dict, query: str) -> Location | None:
        try:
            raw_lng, raw_lat = feature["center"]
            lng, lat = float(raw_lng), float(raw_lat)
            if not math.isfinite(lat) or not math.isfinite(lng):
                raise ValueError("coordinates must be finite")
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not self.settings.contains_location(lat, lng):
            return None
        return Location(name=feature.get("place_name", query), lat=lat, lng=lng)

    async def suggest(self, query: str, *, limit: int = 5) -> list[Location]:
        coordinate = self._coordinate_location(query)
        if coordinate is not None:
            return [coordinate]
        token = self.settings.mapbox_access_token
        if not token:
            if self.settings.is_demo and self.settings.allow_mock_mapbox:
                normalized = query.casefold().strip()
                matches: list[Location] = []
                seen: set[tuple[float, float]] = set()
                for key in sorted(KNOWN_DALLAS_LOCATIONS, key=len, reverse=True):
                    if normalized in key or key in normalized:
                        location = KNOWN_DALLAS_LOCATIONS[key]
                        identity = (location.lat, location.lng)
                        if identity not in seen:
                            matches.append(location)
                            seen.add(identity)
                return matches[:limit]
            raise UpstreamServiceError(
                "Address lookup is not configured.",
                details={"provider": "mapbox", "reason": "missing_token"},
            )

        bbox = ",".join(str(value) for value in self.settings.launch_bbox)
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(query, safe='')}.json"
        payload = await self._request(
            url,
            {
                "access_token": token,
                "limit": str(min(max(limit, 1), 5)),
                "autocomplete": "true",
                "bbox": bbox,
                "country": "US",
                "proximity": "-96.7970,32.7767",
                "types": "address,poi,place,postcode,neighborhood,locality",
            },
        )
        return [
            location
            for feature in payload.get("features") or []
            if (location := self._feature_location(feature, query)) is not None
        ][:limit]

    async def geocode(self, query: str) -> Location:
        coordinate = self._coordinate_location(query)
        if coordinate is not None:
            return coordinate
        token = self.settings.mapbox_access_token
        if not token:
            if self.settings.is_demo and self.settings.allow_mock_mapbox:
                return self._demo_geocode(query)
            raise UpstreamServiceError(
                "Address lookup is not configured.", details={"provider": "mapbox", "reason": "missing_token"}
            )

        bbox = ",".join(str(value) for value in self.settings.launch_bbox)
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(query, safe='')}.json"
        payload = await self._request(
            url,
            {
                "access_token": token,
                "limit": "5",
                "bbox": bbox,
                "country": "US",
                "proximity": "-96.7970,32.7767",
                "types": "address,poi,place,postcode,neighborhood,locality",
            },
        )
        features = payload.get("features") or []
        if not features:
            raise OutsideCoverageError(
                f"No matching location was found inside {self.settings.launch_area_name}.",
                details={"query": query, "launch_area": self.settings.launch_area_name},
            )
        location = self._feature_location(features[0], query)
        if location is None:
            try:
                raw_lng, raw_lat = features[0]["center"]
                candidate_lng, candidate_lat = float(raw_lng), float(raw_lat)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise UpstreamServiceError("The address provider returned a malformed location.") from exc
            if not math.isfinite(candidate_lat) or not math.isfinite(candidate_lng):
                raise UpstreamServiceError("The address provider returned a malformed location.")
            raise OutsideCoverageError(
                f"RiskRoute currently covers {self.settings.launch_area_name} only.",
                details={"query": query, "launch_area": self.settings.launch_area_name},
            )
        return location

    async def directions(
        self,
        origin: Location,
        destination: Location,
        preferences: Preferences,
    ) -> list[RawRoute]:
        if not self.settings.contains_location(origin.lat, origin.lng) or not self.settings.contains_location(
            destination.lat, destination.lng
        ):
            raise OutsideCoverageError(f"Both locations must be inside {self.settings.launch_area_name}.")
        token = self.settings.mapbox_access_token
        if not token:
            if self.settings.is_demo and self.settings.allow_mock_mapbox:
                return self._mock_routes(origin, destination, preferences)
            raise UpstreamServiceError(
                "Directions are not configured.", details={"provider": "mapbox", "reason": "missing_token"}
            )

        coordinates = f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coordinates}"
        params = {
            "access_token": token,
            "alternatives": "true",
            "geometries": "geojson",
            "overview": "full",
            "steps": "true",
            "annotations": "distance,duration,speed",
        }
        if preferences.avoid_highways:
            params["exclude"] = "motorway"
        payload = await self._request(url, params)
        routes: list[RawRoute] = []
        for index, route in enumerate((payload.get("routes") or [])[:3]):
            geometry = route.get("geometry") or {}
            if geometry.get("type") != "LineString" or len(geometry.get("coordinates") or []) < 2:
                continue
            try:
                duration_seconds = float(route["duration"])
                distance_meters = float(route["distance"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if (
                not math.isfinite(duration_seconds)
                or not math.isfinite(distance_meters)
                or duration_seconds <= 0
                or distance_meters <= 0
            ):
                continue
            routes.append(
                RawRoute(
                    route_id=f"route_{index}",
                    duration_seconds=duration_seconds,
                    distance_meters=distance_meters,
                    geometry=geometry,
                )
            )
        if not routes:
            raise UpstreamServiceError("No drivable route alternatives were returned.", details={"provider": "mapbox"})
        return routes

    def _mock_routes(
        self,
        origin: Location,
        destination: Location,
        preferences: Preferences,
    ) -> list[RawRoute]:
        origin_coord = [origin.lng, origin.lat]
        destination_coord = [destination.lng, destination.lat]
        direct_distance = haversine_distance_meters(origin.lat, origin.lng, destination.lat, destination.lng)
        base_duration = max(420.0, direct_distance / 13.8)
        mid_lat = (origin.lat + destination.lat) / 2
        mid_lng = (origin.lng + destination.lng) / 2
        geometries = [
            [origin_coord, [mid_lng + 0.002, mid_lat + 0.001], destination_coord],
            [origin_coord, [mid_lng - 0.004, mid_lat + 0.006], [destination.lng - 0.003, destination.lat], destination_coord],
            [origin_coord, [origin.lng - 0.006, origin.lat + 0.011], [destination.lng - 0.009, destination.lat + 0.011], destination_coord],
        ]
        multipliers = [1.0, 1.13, 1.24]
        return [
            RawRoute(
                route_id=f"route_{index}",
                duration_seconds=round(base_duration * multipliers[index]),
                distance_meters=round(direct_distance * multipliers[index] * 1.12),
                geometry={"type": "LineString", "coordinates": geometry},
            )
            for index, geometry in enumerate(geometries)
        ]


mapbox_service = MapboxService()
