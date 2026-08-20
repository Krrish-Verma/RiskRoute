from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx


class ArcGISError(RuntimeError):
    pass


class ArcGISFeatureClient:
    def __init__(self, layer_url: str, *, timeout_seconds: float = 90.0, max_retries: int = 3) -> None:
        self.layer_url = layer_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.layer_url}/{path.lstrip('/')}" if path else self.layer_url
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                    response = client.request(method, url, params=params if method == "GET" else None, data=params if method == "POST" else None)
                    response.raise_for_status()
                    payload = response.json()
                if "error" in payload:
                    error = payload["error"]
                    raise ArcGISError(f"ArcGIS {error.get('code')}: {error.get('message')}")
                return payload
            except (httpx.HTTPError, ValueError, ArcGISError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 4))
        raise ArcGISError(f"ArcGIS request failed after retries: {last_error}") from last_error

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("GET", path, params)

    def _post(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, params)

    def metadata(self) -> dict[str, Any]:
        return self._get("", {"f": "json"})

    def object_ids(self, where: str = "1=1") -> list[int]:
        payload = self._get(
            "query",
            {
                "where": where,
                "returnIdsOnly": "true",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        return sorted(int(value) for value in payload.get("objectIds", []))

    def feature_batches(
        self,
        *,
        object_ids: list[int],
        out_fields: list[str],
        batch_size: int = 500,
        out_sr: int = 4326,
    ) -> Iterator[list[dict[str, Any]]]:
        for offset in range(0, len(object_ids), batch_size):
            batch = object_ids[offset : offset + batch_size]
            payload = self._post(
                "query",
                {
                    "objectIds": ",".join(str(value) for value in batch),
                    "outFields": ",".join(out_fields),
                    "returnGeometry": "true",
                    "outSR": str(out_sr),
                    "f": "json",
                },
            )
            yield payload.get("features", [])
