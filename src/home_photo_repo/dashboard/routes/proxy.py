"""Thumbnail / preview proxy for browser image loads.

Browsers can't authenticate to Immich's API (different origin, no api-key
header support in <img> tags). This proxy is the single point that holds
the Immich API key and streams bytes back to the page.

For multi-user setups, the proxy looks up which Immich user owns the asset
and uses their specific API key.  Falls back to the primary key for unknown
owners.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response

from home_photo_repo.immich_client import (
    ImmichAssetNotReadyError,
    ImmichClient,
    ImmichClientError,
)

router = APIRouter()


@router.get("/proxy/thumbnail/{asset_id}")
def get_thumbnail(
    asset_id: str,
    request: Request,
    size: Literal["thumbnail", "preview"] = "thumbnail",
) -> Response:
    deps = request.app.state.deps

    # Resolve the correct API key for this asset's owner.
    with deps.db_conn() as conn:
        row = conn.execute(
            "SELECT uploader_user_id FROM photo_analysis WHERE immich_asset_id = ?",
            (asset_id,),
        ).fetchone()
    owner_id = row["uploader_user_id"] if row else None
    api_key = deps.api_key_for_user(owner_id)

    client = ImmichClient(base_url=deps.immich_base_url, api_key=api_key)
    try:
        try:
            data = client.get_thumbnail(asset_id, size=size)
        except ImmichAssetNotReadyError:
            raise HTTPException(status_code=404, detail="thumbnail not ready") from None
        except ImmichClientError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    finally:
        client.close()
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
