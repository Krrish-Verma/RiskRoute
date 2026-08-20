from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from app.config import Settings
from app.errors import OutsideCoverageError, UpstreamServiceError
from app.models.schemas import Location, Preferences
from app.services import mapbox_service as mapbox_module
from app.services.mapbox_service import MapboxService


def _settings(**overrides) -> Settings:
    values = {
        "APP_MODE": "production",
        "DATABASE_URL": "postgresql+psycopg://riskroute:test@db/riskroute",
        "MAPBOX_ACCESS_TOKEN": "test-token",
        "ALLOW_MOCK_MAPBOX": False,
        "SEED_DEMO_DATA": False,
        "MAPBOX_MAX_RETRIES": 0,
        "MAPBOX_CIRCUIT_FAILURE_THRESHOLD": 3,
        "MAPBOX_CIRCUIT_RESET_SECONDS": 60,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _StubClient:
    def __init__(self, get_result: Callable[[str, dict], httpx.Response]) -> None:
        self.get_result = get_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url: str, params: dict) -> httpx.Response:
        return self.get_result(url, params)


class _PayloadResponse:
    """Response double that can represent non-finite provider JSON values."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def _install_client(monkeypatch, get_result: Callable[[str, dict], httpx.Response]) -> None:
    monkeypatch.setattr(
        mapbox_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _StubClient(get_result),
    )


def _response(status: int, payload: dict, url: str = "https://api.mapbox.test/request") -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("GET", url))


def test_geocode_success_uses_launch_bbox_and_returns_numeric_location(monkeypatch) -> None:
    observed: dict = {}

    def get_result(url: str, params: dict) -> httpx.Response:
        observed.update(url=url, params=params)
        return _response(
            200,
            {"features": [{"place_name": "Dallas City Hall", "center": [-96.7969, 32.7763]}]},
            url,
        )

    _install_client(monkeypatch, get_result)
    location = asyncio.run(MapboxService(_settings()).geocode("Dallas City Hall"))

    assert location == Location(name="Dallas City Hall", lat=32.7763, lng=-96.7969)
    assert observed["params"]["bbox"] == "-97.05,32.6,-96.4,33.15"
    assert observed["params"]["access_token"] == "test-token"
    assert "Dallas%20City%20Hall" in observed["url"]


def test_coordinate_input_supports_current_location_without_provider_token() -> None:
    service = MapboxService(_settings(MAPBOX_ACCESS_TOKEN=""))

    location = asyncio.run(service.geocode("32.901234, -96.812345"))

    assert location.lat == pytest.approx(32.901234)
    assert location.lng == pytest.approx(-96.812345)
    with pytest.raises(OutsideCoverageError):
        asyncio.run(service.geocode("30.2672, -97.7431"))


def test_suggestions_are_bounded_and_skip_malformed_features(monkeypatch) -> None:
    observed: dict = {}

    def get_result(url: str, params: dict) -> httpx.Response:
        observed.update(params)
        return _response(
            200,
            {
                "features": [
                    {"place_name": "Galleria Dallas", "center": [-96.8197, 32.9304]},
                    {"place_name": "Malformed", "center": ["bad", 32.9]},
                    {"place_name": "Austin", "center": [-97.7431, 30.2672]},
                ]
            },
            url,
        )

    _install_client(monkeypatch, get_result)
    suggestions = asyncio.run(MapboxService(_settings()).suggest("Galleria", limit=5))

    assert suggestions == [Location(name="Galleria Dallas", lat=32.9304, lng=-96.8197)]
    assert observed["autocomplete"] == "true"
    assert observed["bbox"] == "-97.05,32.6,-96.4,33.15"


def test_timeout_retries_then_returns_typed_upstream_error(monkeypatch) -> None:
    calls = 0

    def get_result(url: str, params: dict) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", url))

    async def no_sleep(_: float) -> None:
        return None

    _install_client(monkeypatch, get_result)
    monkeypatch.setattr(mapbox_module.asyncio, "sleep", no_sleep)
    service = MapboxService(_settings(MAPBOX_MAX_RETRIES=2))

    with pytest.raises(UpstreamServiceError) as caught:
        asyncio.run(service.geocode("Dallas"))

    assert calls == 3
    assert caught.value.status_code == 503
    assert caught.value.details == {"provider": "mapbox", "reason": "ReadTimeout"}


def test_quota_response_is_not_retried(monkeypatch) -> None:
    calls = 0

    def get_result(url: str, params: dict) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(429, {"message": "Too Many Requests"}, url)

    _install_client(monkeypatch, get_result)
    service = MapboxService(_settings(MAPBOX_MAX_RETRIES=3))

    with pytest.raises(UpstreamServiceError) as caught:
        asyncio.run(service.geocode("Dallas"))

    assert calls == 1
    assert caught.value.details["reason"] == "HTTPStatusError"


@pytest.mark.parametrize("center", [["not-a-number", 32.77], [float("nan"), 32.77], [1]])
def test_malformed_geocode_coordinates_fail_with_typed_error(monkeypatch, center) -> None:
    _install_client(
        monkeypatch,
        lambda url, params: _PayloadResponse({"features": [{"center": center}]}),
    )

    with pytest.raises(UpstreamServiceError, match="malformed location"):
        asyncio.run(MapboxService(_settings()).geocode("Dallas"))


def test_malformed_direction_rows_are_rejected_without_partial_garbage(monkeypatch) -> None:
    origin = Location(name="Downtown", lat=32.7767, lng=-96.7970)
    destination = Location(name="North Dallas", lat=32.9398, lng=-96.8039)
    _install_client(
        monkeypatch,
        lambda url, params: _response(
            200,
            {
                "routes": [
                    {
                        "duration": "unknown",
                        "distance": 1000,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[origin.lng, origin.lat], [destination.lng, destination.lat]],
                        },
                    }
                ]
            },
            url,
        ),
    )

    with pytest.raises(UpstreamServiceError, match="No drivable route"):
        asyncio.run(MapboxService(_settings()).directions(origin, destination, Preferences()))


def test_production_never_uses_demo_geocoding_or_routes_without_token() -> None:
    settings = _settings(MAPBOX_ACCESS_TOKEN="", ALLOW_MOCK_MAPBOX=True)
    service = MapboxService(settings)
    origin = Location(name="Downtown", lat=32.7767, lng=-96.7970)
    destination = Location(name="North Dallas", lat=32.9398, lng=-96.8039)

    with pytest.raises(UpstreamServiceError) as geocode_error:
        asyncio.run(service.geocode("Dallas"))
    with pytest.raises(UpstreamServiceError) as directions_error:
        asyncio.run(service.directions(origin, destination, Preferences()))

    assert geocode_error.value.details["reason"] == "missing_token"
    assert directions_error.value.details["reason"] == "missing_token"


def test_circuit_opens_after_configured_failure_threshold(monkeypatch) -> None:
    calls = 0

    def get_result(url: str, params: dict) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=httpx.Request("GET", url))

    _install_client(monkeypatch, get_result)
    service = MapboxService(_settings(MAPBOX_CIRCUIT_FAILURE_THRESHOLD=1))

    with pytest.raises(UpstreamServiceError) as first:
        asyncio.run(service.geocode("Dallas"))
    with pytest.raises(UpstreamServiceError) as second:
        asyncio.run(service.geocode("Dallas"))

    assert first.value.details["reason"] == "ConnectError"
    assert second.value.details["reason"] == "circuit_open"
    assert second.value.details["retry_after_seconds"] >= 1
    assert calls == 1
