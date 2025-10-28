from __future__ import annotations

"""Translate structured vibe slots into Spotify recommendation parameters."""

import logging

from typing import Dict, List, Optional, Tuple

from .vibe_schema import VibeSlots

logger = logging.getLogger(__name__)

BASE: Dict[str, float] = {
    "valence": 0.5,
    "energy": 0.5,
    "danceability": 0.5,
    "acousticness": 0.5,
    "instrumentalness": 0.2,
    "liveness": 0.12,
    "speechiness": 0.05,
    "tempo_bpm": 100.0,
}

MOOD: Dict[str, Dict[str, float]] = {
    "romantic": {"valence": 0.20, "energy": -0.10, "acousticness": 0.10, "danceability": 0.05},
    "melancholic": {"valence": -0.20, "energy": -0.10, "acousticness": 0.10},
    "happy": {"valence": 0.25, "energy": 0.15, "danceability": 0.10, "tempo_bpm": 10.0},
    "energetic": {"energy": 0.30, "danceability": 0.10, "valence": 0.10, "tempo_bpm": 20.0},
    "calm": {"energy": -0.20, "valence": 0.05, "instrumentalness": 0.10, "tempo_bpm": -20.0},
    "dark": {"valence": -0.25, "energy": 0.05, "acousticness": -0.10, "speechiness": -0.02},
    "nostalgic": {"valence": 0.05, "danceability": -0.05, "acousticness": 0.05},
    "confident": {"energy": 0.20, "valence": 0.15, "danceability": 0.10, "tempo_bpm": 12.0},
    "angry": {"energy": 0.35, "valence": -0.25, "danceability": 0.05, "tempo_bpm": 25.0},
    "hopeful": {"valence": 0.18, "energy": 0.08, "danceability": 0.05},
    "bittersweet": {"valence": -0.05, "energy": -0.05, "acousticness": 0.08},
}

ACTIVITY: Dict[str, Dict[str, float]] = {
    "coding": {"instrumentalness": 0.50, "speechiness": -0.02, "energy": -0.10, "tempo_bpm": -20.0},
    "studying": {"instrumentalness": 0.45, "energy": -0.10, "tempo_bpm": -15.0},
    "party": {"energy": 0.30, "danceability": 0.20, "tempo_bpm": 20.0, "instrumentalness": -0.10},
    "dinner": {"energy": -0.10, "acousticness": 0.10, "danceability": 0.05, "tempo_bpm": -10.0},
    "workout": {"energy": 0.35, "danceability": 0.10, "tempo_bpm": 25.0},
    "drive": {"energy": 0.05, "danceability": 0.05, "tempo_bpm": 8.0},
    "sleep": {"energy": -0.35, "tempo_bpm": -30.0, "liveness": -0.05, "instrumentalness": 0.25},
    "focus": {"instrumentalness": 0.35, "energy": -0.15, "tempo_bpm": -18.0, "speechiness": -0.03},
    "relax": {"energy": -0.15, "acousticness": 0.15, "tempo_bpm": -15.0},
    "run": {"energy": 0.30, "tempo_bpm": 18.0, "danceability": 0.08},
    "dance": {"danceability": 0.30, "energy": 0.20, "tempo_bpm": 22.0},
}

TIME: Dict[str, Dict[str, float]] = {
    "morning": {"energy": 0.10, "valence": 0.10, "tempo_bpm": 10.0},
    "afternoon": {"energy": 0.05, "valence": 0.05},
    "sunset": {"valence": 0.05, "energy": -0.05},
    "evening": {"energy": -0.05, "danceability": 0.05},
    "late_night": {"tempo_bpm": -20.0, "liveness": -0.04, "energy": -0.10},
}

GENRES: Dict[str, List[str]] = {
    # Mood defaults
    "romantic": ["indie-pop", "jazz", "soul"],
    "melancholic": ["acoustic", "singer-songwriter", "indie"],
    "happy": ["pop", "dance", "funk"],
    "energetic": ["edm", "electro-pop", "alt-rock"],
    "calm": ["ambient", "chill", "neo-classical"],
    "dark": ["darkwave", "industrial", "alternative"],
    "nostalgic": ["soft-rock", "classic-rock", "motown"],
    "confident": ["hip-hop", "r-n-b", "trap"],
    "angry": ["metal", "hard-rock", "punk"],
    "hopeful": ["indie-folk", "dream-pop", "gospel"],
    "bittersweet": ["indie", "chamber-pop", "acoustic"],
    # Activity defaults
    "coding": ["lo-fi", "ambient", "downtempo", "minimal-techno"],
    "studying": ["piano", "neo-classical", "ambient"],
    "party": ["dance", "house", "edm", "hip-hop"],
    "dinner": ["jazz", "bossa-nova", "lounge"],
    "workout": ["edm", "dance", "hip-hop"],
    "drive": ["synthwave", "indie-pop", "alt-rock"],
    "sleep": ["ambient", "piano", "lo-fi"],
    "focus": ["ambient", "minimal", "neo-classical"],
    "relax": ["chill", "acoustic", "soul"],
    "run": ["edm", "dance", "hip-hop"],
    "dance": ["dance", "disco", "funk"],
}

LANGUAGE_TO_GENRES: Dict[str, List[str]] = {
    "fr": ["french-pop", "chanson", "jazz"],
    "es": ["latin", "spanish-pop", "reggaeton"],
    "en": ["indie-pop", "alt-rock", "uk-pop"],
    "pt": ["brazilian", "samba", "mpb"],
    "br": ["brazilian", "samba", "bossa-nova"],
    "it": ["italian-pop", "cantautori", "classic-italian-pop"],
    "de": ["german-pop", "electro", "techno"],
    "jp": ["j-pop", "city-pop", "anime"],
    "kr": ["k-pop", "k-hip-hop", "k-indie"],
}

PLACE_TO_LOCALE: Dict[str, str] = {
    "paris": "fr",
    "lyon": "fr",
    "marseille": "fr",
    "madrid": "es",
    "barcelona": "es",
    "mexico": "es",
    "buenos aires": "es",
    "rio": "pt",
    "rio de janeiro": "pt",
    "sao paulo": "pt",
    "lisbon": "pt",
    "rome": "it",
    "milan": "it",
    "berlin": "de",
    "munich": "de",
    "tokyo": "jp",
    "kyoto": "jp",
    "seoul": "kr",
    "busan": "kr",
    "new york": "en",
    "london": "en",
    "los angeles": "en",
    "chicago": "en",
}

FALLBACK_GENRES: List[str] = ["pop", "indie", "electronic"]

NUMERIC_KEYS = {"valence", "energy", "danceability", "acousticness", "instrumentalness", "liveness", "speechiness"}


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _clamp_tempo(value: float) -> float:
    return max(50.0, min(160.0, round(value, 1)))


def _apply_deltas(acc: Dict[str, float], deltas: Optional[Dict[str, float]]) -> None:
    if not deltas:
        return
    for key, change in deltas.items():
        if key == "tempo_bpm":
            acc["tempo_bpm"] = acc.get("tempo_bpm", BASE["tempo_bpm"]) + change
        else:
            acc[key] = acc.get(key, BASE.get(key, 0.0)) + change


def _detect_locale(slots: VibeSlots) -> Optional[str]:
    code: Optional[str] = None
    if slots.language_or_locale:
        candidate = slots.language_or_locale.strip().lower()
        if len(candidate) >= 2:
            code = candidate[:2]
    if not code and slots.place:
        place = slots.place.strip().lower()
        if place:
            for name, loc in PLACE_TO_LOCALE.items():
                if name in place:
                    code = loc
                    break
    return code


def _normalise_hint(text: str) -> str:
    return text.strip().lower().replace(" ", "-")


def _extend_unique(target: List[str], values: List[str]) -> None:
    for val in values:
        norm = val.strip().lower()
        if not norm:
            continue
        if norm not in target:
            target.append(norm)


def slots_to_targets_and_genres(slots: VibeSlots) -> Tuple[Dict[str, float], List[str]]:
    features = dict(BASE)

    _apply_deltas(features, MOOD.get(slots.mood))
    if slots.activity:
        _apply_deltas(features, ACTIVITY.get(slots.activity))
    if slots.time_of_day and slots.time_of_day != "none":
        _apply_deltas(features, TIME.get(slots.time_of_day))

    intensity_delta = (slots.intensity - 3) * 0.08
    features["energy"] = features.get("energy", BASE["energy"]) + intensity_delta
    tempo_delta = (slots.intensity - 3) * 6.0
    features["tempo_bpm"] = features.get("tempo_bpm", BASE["tempo_bpm"]) + tempo_delta

    for key in NUMERIC_KEYS:
        val = _clamp_unit(features.get(key, BASE.get(key, 0.5)))
        if key == "energy":
            val = min(val, 0.92)
        elif key == "tempo_bpm":
            pass
        elif key != "speechiness":
            val = min(val, 0.97)
        features[key] = val
    features["tempo_bpm"] = _clamp_tempo(features.get("tempo_bpm", BASE["tempo_bpm"]))

    targets = {f"target_{name}": value for name, value in features.items() if name != "tempo_bpm"}
    targets["target_tempo"] = features["tempo_bpm"]

    seeds: List[str] = []
    if slots.style_hints:
        hints = [_normalise_hint(h) for h in slots.style_hints if h]
        _extend_unique(seeds, [h for h in hints if h])

    locale = _detect_locale(slots)
    if locale and locale in LANGUAGE_TO_GENRES:
        _extend_unique(seeds, LANGUAGE_TO_GENRES[locale])

    if slots.place and not locale:
        place = slots.place.strip().lower()
        for name, loc in PLACE_TO_LOCALE.items():
            if name in place and loc in LANGUAGE_TO_GENRES:
                _extend_unique(seeds, LANGUAGE_TO_GENRES[loc])
                break

    _extend_unique(seeds, GENRES.get(slots.mood, []))
    if slots.activity:
        _extend_unique(seeds, GENRES.get(slots.activity, []))

    if len(seeds) < 3:
        _extend_unique(seeds, FALLBACK_GENRES)

    if len(seeds) == 1:
        _extend_unique(seeds, FALLBACK_GENRES)

    limited_seeds = seeds[:5]
    logger.info("Mapped slots to Spotify params", extra={"mood": slots.mood, "activity": slots.activity, "targets": targets, "seeds": limited_seeds})

    return targets, limited_seeds
