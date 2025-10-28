import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

import backend.main as backend_main
from backend.vibe_engine import generate_playlist_params


@pytest.fixture(autouse=True)
def disable_embeddings(monkeypatch):
    monkeypatch.setattr("backend.clients.openai_client.get_embeddings", lambda texts: None)


def test_generate_playlist_params_safari_selects_afrobeat():
    params, meta = generate_playlist_params("safari adventure in madagascar", None)

    assert params is not None
    assert "afrobeat" in params.get("seed_genres", [])
    assert meta["template_id"] == "afro_safari_adventure"


def test_mood_to_playlist_falls_back_to_legacy(monkeypatch):
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        "backend.main.generate_playlist_params",
        lambda phrase, emoji: (None, {"reason": "forced"}),
    )
    async def fake_recommendations(_: dict):
        return [
            backend_main.Track(
                id=f"track-{i}",
                name=f"Example {i}",
                artists=["Test Artist"],
                preview_url=None,
                external_url=None,
                image_url=None,
                duration_ms=180000,
            )
            for i in range(25)
        ]

    async def fake_search_fallback(*args, **kwargs):
        return []

    monkeypatch.setattr("backend.main.get_recommendations", fake_recommendations)
    monkeypatch.setattr("backend.main.search_tracks_fallback", fake_search_fallback)
    monkeypatch.setattr(
        "backend.main.get_available_genre_seeds",
        lambda: {
            "pop",
            "dance",
            "latin",
            "reggaeton",
            "afrobeat",
            "world-music",
            "chill",
            "study",
            "edm",
            "electro",
            "work-out",
            "hip-hop",
            "r-n-b",
            "funk",
            "road-trip",
            "indie-pop",
            "ambient",
        },
    )

    response = client.post("/api/mood-to-playlist", json={"mood": "unknown vibe"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["source"] == "legacy_rules"
    assert payload["params"]["seed_genres"] == ["pop"]


def test_vibe_endpoint_uses_template_engine(monkeypatch):
    client = TestClient(backend_main.app)

    async def fake_recommendations(_: dict):
        return [
            backend_main.Track(
                id=f"track-{i}",
                name=f"Example {i}",
                artists=["Test Artist"],
                preview_url=None,
                external_url=None,
                image_url=None,
                duration_ms=180000,
            )
            for i in range(25)
        ]

    async def fake_search_fallback(*args, **kwargs):
        return []

    monkeypatch.setattr("backend.main.get_recommendations", fake_recommendations)
    monkeypatch.setattr("backend.main.search_tracks_fallback", fake_search_fallback)
    monkeypatch.setattr(
        "backend.main.get_available_genre_seeds",
        lambda: {
            "pop",
            "dance",
            "latin",
            "reggaeton",
            "afrobeat",
            "world-music",
            "chill",
            "study",
            "edm",
            "electro",
            "work-out",
            "hip-hop",
            "r-n-b",
            "funk",
            "road-trip",
            "indie-pop",
            "ambient",
        },
    )

    response = client.post("/api/vibe", json={"phrase": "safari adventure in madagascar"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "template"
    assert payload["meta"]["source"] == "template_engine"
    assert "afrobeat" in payload["seed_genres"]
