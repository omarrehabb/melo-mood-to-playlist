from __future__ import annotations

"""High level helpers that orchestrate LLM parsing and legacy fallbacks."""

import logging

from typing import Optional, get_args

from pydantic import ValidationError

from .clients import openai_client
from .vibe_schema import ActivityLiteral, MoodLiteral, TimeLiteral, VibeSlots

logger = logging.getLogger(__name__)

LEGACY_PHRASES = {
    "focus",
    "study",
    "studying",
    "chill",
    "lofi",
    "lo-fi",
    "happy",
    "sad",
    "angry",
    "romantic",
    "workout",
    "party",
    "energetic",
    "calm",
    "sleep",
    "relax",
    "drive",
}

VALID_MOODS = set(get_args(MoodLiteral))
VALID_ACTIVITIES = set(get_args(ActivityLiteral))
VALID_TIMES = set(get_args(TimeLiteral))

MOOD_ALIASES = {
    "focused": "calm",
    "focus": "calm",
    "productive": "confident",
}

ACTIVITY_ALIASES = {
    "coding session": "coding",
    "programming": "coding",
    "study": "studying",
    "jiujitsu": "workout",
    "jiu-jitsu": "workout",
    "martial arts": "workout",
}

TIME_ALIASES = {
    "night": "late_night",
    "midnight": "late_night",
    "evening late": "late_night",
}


def _coerce_enum_value(raw: Optional[str], valid: set[str], aliases: dict[str, str], field: str) -> Optional[str]:
    if raw is None:
        return None
    key = raw.strip().lower()
    if not key:
        return None
    if key in valid:
        return key
    if key in aliases:
        coerced = aliases[key]
        logger.info(
            "Coerced unsupported value",
            extra={"field": field, "input": key, "output": coerced},
        )
        return coerced
    return None


def _sanitize_payload(payload: dict) -> dict:
    data = dict(payload)

    mood_value = data.get("mood")
    coerced_mood = _coerce_enum_value(mood_value, VALID_MOODS, MOOD_ALIASES, "mood")
    if coerced_mood:
        data["mood"] = coerced_mood

    activity_value = data.get("activity")
    coerced_activity = _coerce_enum_value(activity_value, VALID_ACTIVITIES, ACTIVITY_ALIASES, "activity")
    if coerced_activity or activity_value is None:
        data["activity"] = coerced_activity

    time_value = data.get("time_of_day")
    coerced_time = _coerce_enum_value(time_value, VALID_TIMES, TIME_ALIASES, "time_of_day")
    if coerced_time:
        data["time_of_day"] = coerced_time

    return data


def is_legacy_phrase(raw: str) -> bool:
    phrase = (raw or "").strip().lower()
    if not phrase:
        return True
    return phrase in LEGACY_PHRASES


def parse_phrase(raw_phrase: str) -> Optional[VibeSlots]:
    phrase = (raw_phrase or "").strip()
    if not phrase:
        return None

    if is_legacy_phrase(phrase):
        logger.info("LLM parser skipped legacy phrase", extra={"phrase": phrase})
        return None

    logger.info("Invoking LLM parser", extra={"phrase": phrase})
    payload = openai_client.parse_phrase_to_slots(phrase)
    if not payload:
        logger.info("LLM parser returned no payload", extra={"phrase": phrase})
        return None

    try:
        slots = VibeSlots.model_validate(_sanitize_payload(payload))
    except ValidationError as exc:
        logger.warning("LLM payload failed validation", extra={"phrase": phrase, "error": str(exc)[:200]})
        return None

    # Remove empty style hints to ensure downstream determinism
    slots.style_hints = [h for h in slots.style_hints if h]
    logger.info("LLM parser succeeded", extra={"phrase": phrase, "confidence": slots.confidence, "mood": slots.mood})
    return slots
