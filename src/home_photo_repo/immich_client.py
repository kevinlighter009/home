"""Thin HTTP client for the subset of Immich's REST API we use."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from home_photo_repo.immich_types import ImmichAsset


class ImmichClientError(RuntimeError):
    """Raised when Immich returns a non-2xx response or a malformed body."""


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string from Immich and normalize to UTC.

    Immich returns timestamps with either `Z` or an explicit offset;
    `fromisoformat` in 3.11+ handles both once `Z` is replaced with `+00:00`.
    We always normalize to UTC so equality comparisons in tests work.
    """
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class ImmichClient:
    """Minimal Immich client. All methods are synchronous; the worker is sequential."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key, "Accept": "application/json"}
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ImmichClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    # --- public API ---------------------------------------------------------

    def search_metadata(
        self,
        *,
        updated_after: datetime,
        last_id: str = "",
        size: int = 100,
        order: str = "asc",
    ) -> list[ImmichAsset]:
        """Fetch assets updated after `updated_after`, oldest-first by default.

        Tied-timestamp handling: Immich's `updatedAfter` filter is strict, but
        when multiple assets share `updated_at`, the filter alone can't tell
        Immich which of them we've already seen. So we request `updated_after=ts`
        and post-filter on the client to drop any item whose
        `(updated_at, id) <= (ts, last_id)`.
        """
        body = {
            "updatedAfter": updated_after.isoformat(),
            "withExif": True,
            "order": order,
            "size": size,
        }
        resp = self._post("/api/search/metadata", json=body)
        try:
            items = resp["assets"]["items"]
        except (KeyError, TypeError) as e:
            raise ImmichClientError(f"unexpected response shape: {e!r}") from e
        parsed = [self._parse_asset(item) for item in items]
        # Drop items the cursor has already passed.
        return [a for a in parsed if (a.updated_at, a.id) > (updated_after, last_id)]

    # --- internals ----------------------------------------------------------

    def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.post(url, headers=self._headers, json=json)
        except httpx.HTTPError as e:
            raise ImmichClientError(f"network error calling {path}: {e!r}") from e
        if response.status_code >= 400:
            raise ImmichClientError(
                f"Immich {path} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ImmichClientError(f"non-JSON response from {path}") from e
        if not isinstance(data, dict):
            raise ImmichClientError(f"non-object JSON response from {path}")
        return data

    @staticmethod
    def _parse_asset(item: dict[str, Any]) -> ImmichAsset:
        asset_id = item.get("id", "<unknown>")
        try:
            exif = item.get("exifInfo") or {}
            updated_at_raw = item.get("updatedAt")
            updated_at = _parse_dt(updated_at_raw)
            if updated_at is None:
                raise ImmichClientError(
                    f"asset {asset_id!r} missing required field 'updatedAt'"
                )
            return ImmichAsset(
                id=item["id"],
                owner_id=item.get("ownerId", ""),
                original_file_name=item.get("originalFileName", ""),
                updated_at=updated_at,
                taken_at=_parse_dt(exif.get("dateTimeOriginal")),
                latitude=exif.get("latitude"),
                longitude=exif.get("longitude"),
                file_created_at=_parse_dt(item.get("fileCreatedAt")),
            )
        except ImmichClientError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise ImmichClientError(
                f"failed to parse asset {asset_id!r}: {e!r}"
            ) from e


__all__ = ["ImmichClient", "ImmichClientError"]
