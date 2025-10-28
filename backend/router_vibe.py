from __future__ import annotations

"""FastAPI router that exposes the curated vibe engine alongside the legacy flow."""

import logging

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import main as legacy_backend
from .vibe_engine import generate_playlist_params

router = APIRouter(prefix="/api", tags=["vibe"])

logger = logging.getLogger(__name__)


class VibeRequest(BaseModel):
    phrase: str
    user_id: Optional[int] = None
    exclude_ids: Optional[List[str]] = None
    exclude_keys: Optional[List[str]] = None


class VibeResponse(BaseModel):
    source: Literal["template", "legacy"]
    targets: dict
    seed_genres: List[str]
    tracks: List[legacy_backend.Track]
    meta: Optional[dict] = None


async def _fetch_tracks(params: dict, exclude_ids: Optional[List[str]], exclude_keys: Optional[List[str]]):
    tracks = await legacy_backend.get_recommendations(params)

    if not exclude_ids and not exclude_keys:
        return tracks

    exclude_ids_set = set(exclude_ids or [])
    exclude_keys_set = set(exclude_keys or [])
    filtered = []
    for track in tracks:
        if track.id in exclude_ids_set:
            continue
        key = legacy_backend._base_track_key(track)
        if key and key in exclude_keys_set:
            continue
        filtered.append(track)
    return filtered


@router.post("/vibe", response_model=VibeResponse)
async def vibe(body: VibeRequest, db: Session = Depends(legacy_backend.get_db)):
    phrase = (body.phrase or "").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Phrase is required")

    logger.info("/api/vibe received", extra={"phrase": phrase, "user_id": body.user_id})

    exclude_ids = body.exclude_ids or []
    exclude_keys = body.exclude_keys or []

    params, diagnostics = generate_playlist_params(phrase, None)
    response_source = "template"
    engine_source = "template_engine"
    if not params:
        response_source = "legacy"
        engine_source = "legacy_rules"
        params = legacy_backend.mood_to_params(phrase)
        diagnostics = {**(diagnostics or {}), "source": engine_source}
    else:
        diagnostics = {**(diagnostics or {}), "source": engine_source}

    seeds = legacy_backend.normalize_seed_genres(params.get("seed_genres", ["pop"]))
    params["seed_genres"] = seeds
    tracks = await _fetch_tracks(params, exclude_ids, exclude_keys)
    targets = {k: v for k, v in params.items() if k.startswith("target_")}

    logger.info(
        "vibe response resolved",
        extra={
            "phrase": phrase,
            "source": response_source,
            "seed_genres": seeds,
            "targets": targets,
            "track_count": len(tracks),
            "meta": diagnostics,
        },
    )

    if body.user_id:
        history = legacy_backend.MoodHistory(
            user_id=body.user_id,
            mood_text=phrase,
            params=params,
            tracks=[t.model_dump() for t in tracks],
        )
        db.add(history)
        db.commit()

    return VibeResponse(
        source=response_source,
        targets=targets,
        seed_genres=seeds,
        tracks=tracks,
        meta=diagnostics,
    )
