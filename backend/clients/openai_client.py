from __future__ import annotations

"""Thin OpenAI client wrapper dedicated to slot extraction via Responses API."""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

try:
    from openai import APIStatusError, OpenAI
except ImportError:  # pragma: no cover
    from openai import OpenAI  # type: ignore
    from openai.error import APIStatusError  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

SYSTEM_MESSAGE = (
    "You convert free-text music requests into a JSON object matching the provided schema. "
    "Output ONLY JSON. Use these enumerations exactly: "
    "mood in ['romantic','melancholic','happy','energetic','calm','dark','nostalgic','confident','angry','hopeful','bittersweet']; "
    "activity in ['coding','studying','party','dinner','workout','drive','sleep','focus','relax','run','dance']; "
    "time_of_day in ['morning','afternoon','sunset','evening','late_night','none']. "
    "When the phrase suggests something outside the list, choose the closest supported value (e.g., jiujitsu -> workout). "
    "Include 1-3 style_hints if useful, prefer ISO language codes for language_or_locale. Be conservative with confidence."
)

FEW_SHOT_PAIRS: tuple[tuple[str, Dict[str, Any]], ...] = (
    (
        "romantic date in paris at sunset, a bit classy",
        {
            "mood": "romantic",
            "activity": "dinner",
            "time_of_day": "sunset",
            "place": "paris",
            "era": None,
            "intensity": 3,
            "style_hints": ["jazz", "chanson"],
            "language_or_locale": "fr",
            "confidence": 0.82,
        },
    ),
    (
        "late night coding, need deep focus, no lyrics",
        {
            "mood": "calm",
            "activity": "coding",
            "time_of_day": "late_night",
            "place": None,
            "era": None,
            "intensity": 2,
            "style_hints": ["lo-fi", "ambient", "minimal"],
            "language_or_locale": "en",
            "confidence": 0.87,
        },
    ),
    (
        "late night jiujitsu drilling session",
        {
            "mood": "energetic",
            "activity": "workout",
            "time_of_day": "late_night",
            "place": "dojo",
            "era": None,
            "intensity": 4,
            "style_hints": ["electronic", "hip-hop"],
            "language_or_locale": "en",
            "confidence": 0.78,
        },
    ),
)

_client: Optional[OpenAI] = None


def _get_client() -> Optional[OpenAI]:
    global _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=api_key)
    return _client


def _build_prompt(phrase: str) -> str:
    lines = [SYSTEM_MESSAGE]
    for user_text, payload in FEW_SHOT_PAIRS:
        lines.append(f"Input: {user_text}")
        lines.append(f"Output: {json.dumps(payload, separators=(',', ':'))}")
    lines.append(f"Input: {phrase}")
    lines.append("Output:")
    return "\n".join(lines)


def _extract_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text

    chunks: list[str] = []
    for output in getattr(resp, "output", []) or []:
        for item in getattr(output, "content", []) or []:
            piece = getattr(item, "text", None)
            value = None
            if isinstance(piece, str):
                value = piece
            elif piece is not None:
                value = getattr(piece, "value", None)
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(chunks).strip()


def parse_phrase_to_slots(phrase: str) -> Optional[Dict[str, Any]]:
    """Return parsed JSON dict from the OpenAI Responses API, or None on failure."""
    client = _get_client()
    if client is None:
        logger.warning("OPENAI_API_KEY not configured; skipping LLM call")
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    logger.info("Calling OpenAI Responses API", extra={"model": model})

    prompt = _build_prompt(phrase)

    try:
        resp = client.responses.create(
            model=model,
            input=prompt,
            #temperature=0.1,
            #max_output_tokens=300,
            #response_format={"type": "json_object"},
        )
        print("OpenAI response object:", resp)
    except APIStatusError as e:  # 4xx/5xx from OpenAI
        status = getattr(e, "status_code", None)
        body = None
        if getattr(e, "response", None) is not None:
            try:
                body = e.response.json()
            except Exception:
                body = getattr(e.response, "text", None)
        print("HTTP", status, "|", body)
        logger.error(
            "OpenAI 4xx/5xx",
            extra={"status": status, "body": body, "error": str(e)[:500]},
        )
        return None
    except Exception as e:
        logger.error(
            "OpenAI call failed",
            exc_info=True,
            extra={"error": str(e)[:500], "exception_type": type(e).__name__},
        )
        return None

    raw = _extract_text(resp)
    print("OpenAI response text:", raw)
    if not raw:
        logger.warning("Empty text in Responses API output")
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse JSON from Responses API", extra={"error": str(exc)[:200]})
        return None

    logger.info("Received response from OpenAI Responses API")
    return parsed


def get_embeddings(texts: Sequence[str]) -> Optional[List[List[float]]]:
    """Return embeddings for provided texts using the configured OpenAI client."""
    client = _get_client()
    if client is None:
        return None

    cleaned: List[str] = [t for t in texts if isinstance(t, str) and t.strip()]
    if not cleaned:
        return None

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    try:
        resp = client.embeddings.create(model=model, input=cleaned)
    except APIStatusError as exc:  # pragma: no cover - network failure paths
        logger.error(
            "OpenAI embeddings request failed",
            extra={
                "status": getattr(exc, "status_code", None),
                "error": str(exc)[:500],
            },
        )
        return None
    except Exception as exc:  # pragma: no cover
        logger.error(
            "OpenAI embeddings request errored",
            exc_info=True,
            extra={"error": str(exc)[:500], "exception_type": type(exc).__name__},
        )
        return None

    vectors: List[List[float]] = []
    for item in getattr(resp, "data", []):
        emb = getattr(item, "embedding", None)
        if isinstance(emb, list):
            try:
                vectors.append([float(x) for x in emb])
            except (TypeError, ValueError):
                continue
    if len(vectors) != len(cleaned):
        logger.warning(
            "Embedding response count mismatch",
            extra={"requested": len(cleaned), "received": len(vectors)},
        )
    return vectors
