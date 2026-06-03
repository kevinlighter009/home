"""Thin HTTP client for the subset of Immich's REST API we use."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from home_photo_repo.immich_types import ImmichAsset


class ImmichClientError(RuntimeError):
    """Raised when Immich returns a non-2xx response or a malformed body."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ImmichAssetNotReadyError(ImmichClientError):
    """Raised on 404 from asset binary endpoints — Immich's processing job
    (thumbnail / metadata / transcoding) hasn't completed for this asset yet.

    Distinct from a general `ImmichClientError` so callers can choose to
    defer + retry instead of treating it as a permanent failure. Immich
    bumps the asset's `updated_at` when each job completes, so the next
    poll cycle naturally re-fetches the asset and the call succeeds."""


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
        body: dict[str, Any] = {
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

    def search_all_assets(
        self,
        *,
        page: int = 1,
        size: int = 100,
        order: str = "asc",
    ) -> tuple[list[ImmichAsset], int | None]:
        """Fetch a page of ALL assets with no date filter.

        Returns (assets, next_page) where next_page is None on the last page.
        Used for initial backfill when the updatedAfter cursor cannot reach
        historical assets (e.g. all photos imported in one batch share the
        same updatedAt, leaving the cursor stranded past them all).
        """
        body: dict[str, Any] = {
            "withExif": True,
            "order": order,
            "size": size,
            "page": page,
        }
        resp = self._post("/api/search/metadata", json=body)
        try:
            assets_resp = resp["assets"]
            items = assets_resp["items"]
            raw_next = assets_resp.get("nextPage")
            next_page = int(raw_next) if raw_next is not None else None
        except (KeyError, TypeError, ValueError) as e:
            raise ImmichClientError(f"unexpected response shape: {e!r}") from e
        return [self._parse_asset(item) for item in items], next_page

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        """Fetch an asset's thumbnail or preview.

        `size` is one of:
          - "thumbnail" (~250px, fast, Stage A)
          - "preview" (~1440px, Stage B)
        """
        if size not in ("thumbnail", "preview"):
            raise ValueError(f"invalid size {size!r}; expected 'thumbnail' or 'preview'")
        return self._get_bytes(
            f"/api/assets/{asset_id}/thumbnail", params={"size": size}
        )

    def get_original(self, asset_id: str) -> bytes:
        """Fetch an asset's original full-resolution bytes."""
        return self._get_bytes(f"/api/assets/{asset_id}/original")

    def get_asset_statistics(self) -> dict[str, int]:
        """Return asset counts for the authenticated user.

        Returns a dict with keys: ``images``, ``videos``, ``total``.
        Calls GET /api/assets/statistics (user-scoped — each key sees only
        its own assets).
        """
        url = f"{self._base_url}/api/assets/statistics"
        try:
            response = self._client.get(url, headers=self._headers)
        except httpx.HTTPError as e:
            raise ImmichClientError(
                f"network error calling /api/assets/statistics: {e!r}"
            ) from e
        if response.status_code >= 400:
            raise ImmichClientError(
                f"Immich /api/assets/statistics returned {response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ImmichClientError(
                "non-JSON response from /api/assets/statistics"
            ) from e
        return {
            "images": int(data.get("images", 0)),
            "videos": int(data.get("videos", 0)),
            "total": int(data.get("total", 0)),
        }

    def get_me(self) -> dict[str, str]:
        """Return the authenticated user's id, name, and email."""
        url = f"{self._base_url}/api/users/me"
        try:
            response = self._client.get(url, headers=self._headers)
        except httpx.HTTPError as e:
            raise ImmichClientError(f"network error calling /api/users/me: {e!r}") from e
        if response.status_code >= 400:
            raise ImmichClientError(
                f"Immich /api/users/me returned {response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ImmichClientError("non-JSON response from /api/users/me") from e
        return {
            "id": data["id"],
            "name": data.get("name", ""),
            "email": data.get("email", ""),
        }

    def _get_bytes(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> bytes:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.get(url, headers=self._headers, params=params or {})
        except httpx.HTTPError as e:
            raise ImmichClientError(f"network error calling {path}: {e!r}") from e
        if response.status_code == 404:
            raise ImmichAssetNotReadyError(
                f"Immich {path} returned 404 (asset processing job pending?)",
                status_code=404,
            )
        if response.status_code >= 400:
            raise ImmichClientError(
                f"Immich {path} returned {response.status_code}",
                status_code=response.status_code,
            )
        return response.content

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
