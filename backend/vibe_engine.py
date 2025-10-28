from __future__ import annotations

"""Feature-driven vibe selection engine that replaces LLM JSON generation."""

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .clients import openai_client
from .vibe_templates import VIBE_TEMPLATES, VibeTemplate

logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
_CACHE_PATH = os.path.join(_CACHE_DIR, "template_embeddings.json")

DEFAULT_TARGETS: Dict[str, float] = {
    "target_energy": 0.6,
    "target_valence": 0.55,
    "target_tempo": 112,
    "target_danceability": 0.58,
}

KEYWORD_ALIASES: Dict[str, Sequence[str]] = {
    "madagascar": ["madagascar", "malagasy", "lemur", "safari", "africa"],
    "safari": ["safari", "wildlife", "savanna", "adventure", "africa"],
    "savanna": ["safari", "savanna", "grassland"],
    "hiit": ["hiit", "intense", "workout"],
    "afrobeats": ["afrobeat"],
    "focus": ["focus", "concentration", "study"],
    "coding": ["coding", "programming", "focus"],
    "rainy": ["rainy", "rain", "storm"],
    "storm": ["storm", "dramatic", "dark"],
    "sunset": ["sunset", "golden-hour"],
    "sunrise": ["sunrise", "dawn", "morning"],
    "night": ["night", "late-night", "midnight"],
    "party": ["party", "celebration", "dance"],
    "festival": ["festival", "party", "celebration"],
    "yoga": ["yoga", "meditation", "calm"],
    "chill": ["chill", "relax", "calm"],
    "study": ["study", "focus", "reading"],
    "beach": ["beach", "tropical", "ocean"],
    "roadtrip": ["roadtrip", "road-trip", "drive"],
    "drive": ["drive", "roadtrip", "night-drive"],
    "caribbean": ["caribbean", "island"],
    "brazil": ["brazil", "rio"],
    "samba": ["samba", "brazil"],
    "techno": ["techno", "club"],
    "hiphop": ["hip-hop", "rap"],
}

PHRASE_KEYWORDS: Dict[str, Sequence[str]] = {
    "madagascar": ["madagascar", "safari", "wildlife"],
    "indian ocean": ["madagascar", "island"],
    "safari": ["safari", "wildlife", "savanna"],
    "savanna": ["savanna", "wildlife"],
    "coding session": ["coding", "focus"],
    "night market": ["market", "street-food", "night"],
    "street food": ["market", "street-food"],
    "dance party": ["dance", "party"],
    "road trip": ["roadtrip", "drive"],
    "late night": ["night", "late-night"],
    "sunrise": ["sunrise", "morning"],
    "sunset": ["sunset", "evening"],
    "festival": ["festival", "party"],
    "boxing gym": ["boxing", "gym"],
    "yoga class": ["yoga", "calm"],
    "camp fire": ["campfire"],
    "campfire": ["campfire"],
}

EMOJI_KEYWORDS: Dict[str, Sequence[str]] = {
    "🔥": ["intense", "energetic", "party"],
    "🦁": ["safari", "wildlife", "africa"],
    "🐆": ["safari", "wildlife"],
    "🏝️": ["beach", "tropical"],
    "🌅": ["sunrise", "sunset"],
    "🌇": ["sunset", "city"],
    "🌃": ["night", "city"],
    "🌧️": ["rainy", "storm"],
    "☕": ["coffee", "cozy"],
    "💤": ["sleep", "calm"],
    "🧘": ["yoga", "meditation"],
    "💪": ["workout", "gym"],
    "🎉": ["party", "celebration"],
    "🏕️": ["campfire", "outdoor"],
}

ENERGY_KEYWORDS: Dict[str, Sequence[str]] = {
    "high": ["intense", "energetic", "hype", "powerful", "aggressive", "hiit", "workout", "party", "festival", "dance"],
    "low": ["calm", "chill", "relax", "soothing", "sleep", "wind-down", "ambient", "meditation"],
}

VALENCE_KEYWORDS: Dict[str, Sequence[str]] = {
    "positive": ["happy", "joyful", "uplifting", "hopeful", "sunny", "gratitude"],
    "negative": ["dark", "moody", "storm", "melancholy", "sad"],
}

TEMPO_KEYWORDS: Dict[str, Sequence[str]] = {
    "faster": ["running", "race", "hiit", "workout", "party", "dance", "energetic", "intense"],
    "slower": ["sleep", "calm", "meditation", "chill", "sunset", "late-night"],
}

KEYWORD_SEED_EXPANSIONS: Dict[str, Sequence[str]] = {
    "africa": ["afrobeat", "world-music"],
    "madagascar": ["afrobeat", "world-music"],
    "safari": ["afrobeat", "world-music"],
    "latin": ["latin", "dance"],
    "caribbean": ["dancehall", "latin"],
    "brazil": ["samba", "mpb"],
    "rio": ["samba", "mpb"],
    "yoga": ["new-age", "ambient"],
    "sleep": ["sleep", "ambient"],
    "focus": ["chill", "study"],
    "coding": ["minimal-techno", "ambient"],
    "party": ["dance", "edm"],
    "festival": ["dance", "edm"],
    "rainy": ["rainy-day", "indie"],
    "storm": ["movies", "classical"],
    "campfire": ["acoustic", "folk"],
}


def _normalize_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _extend_keywords(base: Set[str], additions: Iterable[str]) -> None:
    for value in additions:
        cleaned = value.strip().lower()
        if cleaned:
            base.add(cleaned)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass
class TemplateMatch:
    template: VibeTemplate
    score: float
    lexical_overlap: int
    embedding_used: bool


class TemplateIndex:
    def __init__(self) -> None:
        self._templates: Sequence[VibeTemplate] = VIBE_TEMPLATES
        self._embeddings: Dict[str, List[float]] = {}
        self._cache_loaded = False

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        self._cache_loaded = True
        if not os.path.exists(_CACHE_PATH):
            return
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:  # pragma: no cover - cache is optional
            logger.warning("Failed to load template embeddings cache", extra={"error": str(exc)[:200]})
            return
        for key, vec in raw.items():
            if isinstance(vec, list):
                try:
                    self._embeddings[key] = [float(x) for x in vec]
                except (TypeError, ValueError):
                    continue

    def _save_cache(self) -> None:
        if not self._embeddings:
            return
        os.makedirs(_CACHE_DIR, exist_ok=True)
        try:
            with open(_CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._embeddings, fh)
        except Exception as exc:  # pragma: no cover - cache best effort
            logger.warning("Failed to persist template embeddings cache", extra={"error": str(exc)[:200]})

    @staticmethod
    def _build_embedding_text(template: VibeTemplate) -> str:
        return f"{template.title}. {template.description}. Tags: {', '.join(template.tags)}. Genres: {', '.join(template.seed_genres)}."

    def _ensure_embeddings(self) -> None:
        self._load_cache()
        missing = [tpl for tpl in self._templates if tpl.id not in self._embeddings]
        if not missing:
            return
        payloads = [self._build_embedding_text(tpl) for tpl in missing]
        vectors = openai_client.get_embeddings(payloads)
        if not vectors:
            logger.info("Embedding lookup unavailable; continuing with lexical scoring only")
            return
        for tpl, vec in zip(missing, vectors):
            if vec:
                self._embeddings[tpl.id] = vec
        self._save_cache()

    def _embed_phrase(self, phrase: str) -> Optional[List[float]]:
        if not phrase:
            return None
        vectors = openai_client.get_embeddings([phrase])
        if not vectors:
            return None
        vec = vectors[0]
        if not vec:
            return None
        return vec

    def _cosine_similarity(self, a: Sequence[float], b: Sequence[float]) -> Optional[float]:
        if not a or not b:
            return None
        if len(a) != len(b):
            return None
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for av, bv in zip(a, b):
            dot += av * bv
            norm_a += av * av
            norm_b += bv * bv
        if not norm_a or not norm_b:
            return None
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    def select(self, analysis: Dict[str, object]) -> Optional[TemplateMatch]:
        keywords: Set[str] = analysis.get("keywords", set())  # type: ignore[assignment]
        if not isinstance(keywords, set):
            keywords = set()
        phrase: str = str(analysis.get("normalized_text") or "")
        query_embedding: Optional[List[float]] = None
        embedding_used = False

        self._ensure_embeddings()
        if self._embeddings:
            query_embedding = self._embed_phrase(phrase)
            embedding_used = query_embedding is not None

        best: Optional[TemplateMatch] = None
        for template in self._templates:
            overlap = sum(1 for tag in template.tags if tag in keywords)
            lexical_score = overlap / max(4, len(template.tags))
            lexical_score = _clamp(lexical_score, 0.0, 1.0)
            embed_score = None
            if embedding_used:
                tpl_vec = self._embeddings.get(template.id)
                if tpl_vec:
                    embed_score = self._cosine_similarity(query_embedding or [], tpl_vec)
            combined = lexical_score
            if embed_score is not None:
                combined = embed_score * 0.55 + lexical_score * 0.45
            if overlap >= 3:
                combined += 0.1
            elif overlap == 2:
                combined += 0.05
            combined = _clamp(combined, 0.0, 1.2)
            if not best or combined > best.score:
                best = TemplateMatch(template=template, score=combined, lexical_overlap=overlap, embedding_used=embedding_used and embed_score is not None)
        return best


def analyse_phrase(phrase: str, emoji: Optional[str]) -> Dict[str, object]:
    normalized_text = phrase.strip().lower()
    tokens = _normalize_tokens(phrase)
    keywords: Set[str] = set(tokens)

    for token in list(keywords):
        extras = KEYWORD_ALIASES.get(token)
        if extras:
            _extend_keywords(keywords, extras)

    for trigger, extras in PHRASE_KEYWORDS.items():
        if trigger in normalized_text:
            _extend_keywords(keywords, extras)

    if emoji:
        extras = EMOJI_KEYWORDS.get(emoji)
        if extras:
            _extend_keywords(keywords, extras)

    energy_bias = 0.0
    tempo_bias = 0.0
    valence_bias = 0.0

    for token in keywords:
        if token in ENERGY_KEYWORDS["high"]:
            energy_bias += 0.12
            tempo_bias += 6.0
        if token in ENERGY_KEYWORDS["low"]:
            energy_bias -= 0.12
            tempo_bias -= 6.0
        if token in TEMPO_KEYWORDS["faster"]:
            tempo_bias += 8.0
        if token in TEMPO_KEYWORDS["slower"]:
            tempo_bias -= 8.0
        if token in VALENCE_KEYWORDS["positive"]:
            valence_bias += 0.08
        if token in VALENCE_KEYWORDS["negative"]:
            valence_bias -= 0.12

    return {
        "normalized_text": normalized_text,
        "tokens": tokens,
        "keywords": keywords,
        "energy_bias": energy_bias,
        "tempo_bias": tempo_bias,
        "valence_bias": valence_bias,
        "emoji": emoji,
    }


def _apply_bias(params: Dict[str, float], analysis: Dict[str, object]) -> None:
    energy_bias = float(analysis.get("energy_bias", 0.0) or 0.0)
    tempo_bias = float(analysis.get("tempo_bias", 0.0) or 0.0)
    valence_bias = float(analysis.get("valence_bias", 0.0) or 0.0)

    params["target_energy"] = _clamp(params.get("target_energy", DEFAULT_TARGETS["target_energy"]) + energy_bias, 0.05, 0.95)
    params["target_tempo"] = _clamp(params.get("target_tempo", DEFAULT_TARGETS["target_tempo"]) + tempo_bias, 55.0, 150.0)
    params["target_valence"] = _clamp(params.get("target_valence", DEFAULT_TARGETS["target_valence"]) + valence_bias, 0.05, 0.95)


def _expand_seeds(base: Sequence[str], keywords: Set[str]) -> List[str]:
    seeds: List[str] = []
    seen: Set[str] = set()
    for seed in base:
        key = seed.strip().lower()
        if not key or key in seen:
            continue
        seeds.append(key)
        seen.add(key)
    for keyword in keywords:
        extras = KEYWORD_SEED_EXPANSIONS.get(keyword)
        if not extras:
            continue
        for seed in extras:
            key = seed.strip().lower()
            if not key or key in seen:
                continue
            seeds.append(key)
            seen.add(key)
    return seeds


def build_params_from_template(match: TemplateMatch, analysis: Dict[str, object]) -> Tuple[Dict[str, float], Dict[str, object]]:
    params: Dict[str, float] = {**DEFAULT_TARGETS, **match.template.targets}
    keywords: Set[str] = analysis.get("keywords", set())  # type: ignore[assignment]
    if not isinstance(keywords, set):
        keywords = set()
    seeds = _expand_seeds(match.template.seed_genres, keywords)

    _apply_bias(params, analysis)

    if "sunset" in keywords:
        params["target_energy"] = _clamp(params.get("target_energy", 0.6) - 0.05, 0.05, 0.95)
        params["target_tempo"] = _clamp(params.get("target_tempo", 110) - 4.0, 55.0, 150.0)
    if "sunrise" in keywords or "morning" in keywords:
        params["target_valence"] = _clamp(params.get("target_valence", 0.6) + 0.06, 0.05, 0.95)
    if "night" in keywords or "late-night" in keywords:
        params["target_valence"] = _clamp(params.get("target_valence", 0.6) - 0.05, 0.05, 0.95)
    if "storm" in keywords or "dark" in keywords:
        params["target_valence"] = _clamp(params.get("target_valence", 0.6) - 0.12, 0.05, 0.95)
        params["target_energy"] = _clamp(params.get("target_energy", 0.6) + 0.04, 0.05, 0.95)
    if "sleep" in keywords or "meditation" in keywords:
        params["target_energy"] = _clamp(params.get("target_energy", 0.6) - 0.2, 0.05, 0.95)
        params["target_tempo"] = _clamp(params.get("target_tempo", 110) - 12.0, 40.0, 120.0)
    if "workout" in keywords or "run" in keywords:
        params["target_energy"] = _clamp(params.get("target_energy", 0.6) + 0.12, 0.05, 0.95)
        params["target_tempo"] = _clamp(params.get("target_tempo", 110) + 10.0, 55.0, 180.0)
    if "study" in keywords or "focus" in keywords or "coding" in keywords:
        params["target_instrumentalness"] = _clamp(params.get("target_instrumentalness", 0.5) + 0.3, 0.0, 1.0)
        params["target_energy"] = _clamp(params.get("target_energy", 0.6) - 0.08, 0.05, 0.95)

    diagnostics = {
        "template_id": match.template.id,
        "template_title": match.template.title,
        "score": round(match.score, 4),
        "lexical_overlap": match.lexical_overlap,
        "embedding_used": match.embedding_used,
        "keywords": sorted(list(keywords))[:40],
    }
    params["seed_genres"] = seeds[:5]
    return params, diagnostics


def generate_playlist_params(phrase: str, emoji: Optional[str] = None) -> Tuple[Optional[Dict[str, float]], Dict[str, object]]:
    if not phrase and not emoji:
        return None, {"reason": "empty"}
    analysis = analyse_phrase(phrase or "", emoji)
    match = TEMPLATE_INDEX.select(analysis)
    if not match:
        return None, {"reason": "no_match", "analysis": analysis}
    params, diagnostics = build_params_from_template(match, analysis)
    diagnostics["analysis"] = {
        "energy_bias": round(float(analysis.get("energy_bias", 0.0)), 4),
        "tempo_bias": round(float(analysis.get("tempo_bias", 0.0)), 4),
        "valence_bias": round(float(analysis.get("valence_bias", 0.0)), 4),
    }
    return params, diagnostics


TEMPLATE_INDEX = TemplateIndex()

