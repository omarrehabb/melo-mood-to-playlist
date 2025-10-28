from __future__ import annotations

"""Pydantic schema for structured vibe slots extracted by the LLM."""

from typing import List, Optional, Literal

from pydantic import BaseModel, Field, conint, confloat

MoodLiteral = Literal[
    "romantic",
    "melancholic",
    "happy",
    "energetic",
    "calm",
    "dark",
    "nostalgic",
    "confident",
    "angry",
    "hopeful",
    "bittersweet",
]

ActivityLiteral = Literal[
    "coding",
    "studying",
    "party",
    "dinner",
    "workout",
    "drive",
    "sleep",
    "focus",
    "relax",
    "run",
    "dance",
]

TimeLiteral = Literal[
    "morning",
    "afternoon",
    "sunset",
    "evening",
    "late_night",
    "none",
]


class VibeSlots(BaseModel):
    mood: MoodLiteral
    activity: Optional[ActivityLiteral] = None
    time_of_day: Optional[TimeLiteral] = "none"
    place: Optional[str] = None
    era: Optional[str] = None
    intensity: conint(ge=1, le=5) = 3  # 1=very mellow, 5=very intense
    style_hints: List[str] = Field(default_factory=list)
    language_or_locale: Optional[str] = None
    confidence: confloat(ge=0.0, le=1.0)

    class Config:
        json_schema_extra = {
            "description": "Structured slots derived from a free-text vibe phrase."
        }
