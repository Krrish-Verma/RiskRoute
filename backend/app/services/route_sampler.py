from __future__ import annotations

import math
from typing import TypedDict


class SampledPoint(TypedDict):
    lat: float
    lng: float
    distance_meters: float
    index: int


EARTH_RADIUS_M = 6_371_000


def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def interpolate_point(
    start: list[float],
    end: list[float],
    ratio: float,
) -> tuple[float, float]:
    start_lng, start_lat = start
    end_lng, end_lat = end
    lat = start_lat + (end_lat - start_lat) * ratio
    lng = start_lng + (end_lng - start_lng) * ratio
    return lat, lng


def sample_route_points(
    coordinates: list[list[float]],
    interval_meters: float = 100,
) -> list[SampledPoint]:
    if not coordinates:
        return []

    first_lng, first_lat = coordinates[0]
    sampled: list[SampledPoint] = [
        {"lat": first_lat, "lng": first_lng, "distance_meters": 0.0, "index": 0}
    ]

    if len(coordinates) == 1 or interval_meters <= 0:
        return sampled

    distance_so_far = 0.0
    next_target = interval_meters

    for segment_index in range(1, len(coordinates)):
        start = coordinates[segment_index - 1]
        end = coordinates[segment_index]
        segment_distance = haversine_distance_meters(start[1], start[0], end[1], end[0])
        if segment_distance == 0:
            continue

        while next_target <= distance_so_far + segment_distance:
            ratio = (next_target - distance_so_far) / segment_distance
            lat, lng = interpolate_point(start, end, ratio)
            sampled.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "distance_meters": next_target,
                    "index": len(sampled),
                }
            )
            next_target += interval_meters

        distance_so_far += segment_distance

    last_lng, last_lat = coordinates[-1]
    if (
        haversine_distance_meters(
            sampled[-1]["lat"],
            sampled[-1]["lng"],
            last_lat,
            last_lng,
        )
        > 1
    ):
        sampled.append(
            {
                "lat": last_lat,
                "lng": last_lng,
                "distance_meters": distance_so_far,
                "index": len(sampled),
            }
        )

    return sampled
