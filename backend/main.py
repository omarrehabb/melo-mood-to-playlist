import os
import time
import datetime
import re
from typing import List, Optional, Set

import httpx
import orjson
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


# Load environment variables. Prefer backend/.env alongside this file.
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/callback")
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "US")
POSTGRES_URL = os.getenv("POSTGRES_URL", "sqlite:///./melo.db")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")


# -----------------------------------------------------------------------------
# Database setup (SQLAlchemy v2)
# -----------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    spotify_user_id: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    moods: Mapped[List["MoodHistory"]] = relationship(back_populates="user")


class MoodHistory(Base):
    __tablename__ = "mood_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mood_text: Mapped[str] = mapped_column(String(500))
    params: Mapped[dict] = mapped_column(JSON)
    tracks: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="moods")


engine = create_engine(POSTGRES_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------

app = FastAPI(title="Melo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# -----------------------------------------------------------------------------
# Models / Schemas
# -----------------------------------------------------------------------------


class MoodRequest(BaseModel):
    mood: str
    emoji: Optional[str] = None
    user_id: Optional[int] = None
    exclude_ids: Optional[List[str]] = None
    exclude_keys: Optional[List[str]] = None


class Track(BaseModel):
    id: str
    name: str
    artists: List[str]
    preview_url: Optional[str] = None
    external_url: Optional[str] = None
    image_url: Optional[str] = None
    duration_ms: Optional[int] = None


class PlaylistResponse(BaseModel):
    params: dict
    tracks: List[Track]


class SavePlaylistRequest(BaseModel):
    user_id: int
    name: str
    track_ids: List[str]


class HistoryItem(BaseModel):
    id: int
    mood_text: str
    params: dict
    tracks: list
    created_at: Optional[str]


# -----------------------------------------------------------------------------
# Spotify helpers
# -----------------------------------------------------------------------------

_app_token_cache = {"token": None, "expires_at": 0.0}
_genre_seed_cache = {"seeds": set(), "expires_at": 0.0}


def get_spotify_app_token() -> str:
    now = time.time()
    if _app_token_cache["token"] and now < _app_token_cache["expires_at"]:
        return _app_token_cache["token"]
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Spotify credentials not configured")
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to get Spotify token")
    data = resp.json()
    _app_token_cache["token"] = data["access_token"]
    _app_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 30
    return _app_token_cache["token"]


def get_available_genre_seeds() -> Set[str]:
    now = time.time()
    if _genre_seed_cache["seeds"] and now < _genre_seed_cache["expires_at"]:
        return _genre_seed_cache["seeds"]
    token = get_spotify_app_token()
    resp = requests.get(
        "https://api.spotify.com/v1/recommendations/available-genre-seeds",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if resp.status_code != 200:
        # Fallback to a conservative default set if the call fails
        defaults = {
            "pop","dance","house","edm","hip-hop","r-n-b","rock","metal","indie","indie-pop","acoustic","ambient","classical","piano","soul","chill","study","sleep","party","work-out","sad","happy"
        }
        _genre_seed_cache["seeds"] = defaults
        _genre_seed_cache["expires_at"] = now + 3600
        return defaults
    data = resp.json()
    seeds = set(data.get("genres", []) or [])
    _genre_seed_cache["seeds"] = seeds
    _genre_seed_cache["expires_at"] = now + 3600
    return seeds


def normalize_seed_genres(candidates: List[str]) -> List[str]:
    seeds = get_available_genre_seeds()
    normalized = []
    for g in candidates:
        if g in seeds:
            normalized.append(g)
            continue
        # Friendly aliases → valid seeds
        alias_map = {
            "lo-fi": "chill",
            "lofi": "chill",
            "workout": "work-out",
            "rnb": "r-n-b",
        }
        alt = alias_map.get(g)
        if alt and alt in seeds:
            normalized.append(alt)
    # Ensure we always have at least one valid seed
    return normalized or ["pop"]


def mood_to_params(mood: str, emoji: Optional[str] = None) -> dict:
    text = (mood or "").strip().lower()
    e = (emoji or "").strip()
    # Simple keyword/emoji mapping to Spotify recommendations parameters
    # target_tempo ~ bpm, target_energy ~ energy, target_valence ~ positivity
    # target_instrumentalness for focus/ambient vibes
    defaults = {
        "seed_genres": ["pop"],
        "target_tempo": 110,
        "target_energy": 0.6,
        "target_valence": 0.6,
    }
    rules = [
        ("focus", {"seed_genres": ["ambient", "chill"], "target_tempo": 80, "target_energy": 0.3, "target_valence": 0.4, "target_instrumentalness": 0.9}),
        ("study", {"seed_genres": ["classical", "piano"], "target_tempo": 70, "target_energy": 0.2, "target_valence": 0.5, "target_instrumentalness": 0.95}),
        ("chill", {"seed_genres": ["chill", "ambient"], "target_tempo": 85, "target_energy": 0.4, "target_valence": 0.6}),
        ("lofi", {"seed_genres": ["chill"], "target_tempo": 75, "target_energy": 0.3}),
        ("happy", {"seed_genres": ["dance", "pop"], "target_tempo": 125, "target_energy": 0.8, "target_valence": 0.9}),
        ("sad", {"seed_genres": ["acoustic", "indie"], "target_tempo": 90, "target_energy": 0.3, "target_valence": 0.2}),
        ("angry", {"seed_genres": ["metal", "rock"], "target_tempo": 150, "target_energy": 0.95, "target_valence": 0.2}),
        ("romantic", {"seed_genres": ["r-n-b", "soul"], "target_tempo": 95, "target_energy": 0.5, "target_valence": 0.8}),
        ("workout", {"seed_genres": ["edm", "hip-hop"], "target_tempo": 135, "target_energy": 0.9, "target_valence": 0.7}),
        ("party", {"seed_genres": ["dance", "house"], "target_tempo": 128, "target_energy": 0.9, "target_valence": 0.9}),
    ]
    emoji_rules = {
        "😊": {"seed_genres": ["pop"], "target_tempo": 120, "target_energy": 0.8, "target_valence": 0.9},
        "😢": {"seed_genres": ["acoustic"], "target_tempo": 85, "target_energy": 0.3, "target_valence": 0.2},
        "😤": {"seed_genres": ["metal"], "target_tempo": 150, "target_energy": 0.95, "target_valence": 0.2},
        "❤️": {"seed_genres": ["r-n-b"], "target_tempo": 95, "target_energy": 0.5, "target_valence": 0.8},
        "🧘": {"seed_genres": ["ambient"], "target_tempo": 70, "target_energy": 0.2, "target_valence": 0.5, "target_instrumentalness": 0.9},
        "🏋️": {"seed_genres": ["edm"], "target_tempo": 135, "target_energy": 0.9, "target_valence": 0.7},
    }

    params = {**defaults}
    for key, cfg in rules:
        if key in text:
            params.update(cfg)
            break
    if e in emoji_rules:
        params.update(emoji_rules[e])
    # Normalize seeds to valid values
    params["seed_genres"] = normalize_seed_genres(params.get("seed_genres", ["pop"]))
    return params


def _normalize_title(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = str(raw).lower()
    # remove featuring/with credits
    s = re.sub(r"\s*(\(|-|–|—)?\s*(feat\.|featuring|with)\s+[^)\-–—]+\)?", " ", s, flags=re.IGNORECASE)
    # remove bracketed descriptors with version keywords
    s = re.sub(r"\s*[\(\[\{][^\)\]\}]*\b(live|acoustic|remaster(?:ed)?(?:\s*\d{4})?|demo|session|radio\s*edit|edit|version|mono|stereo|deluxe|extended|re[-\s]?recorded|remix)\b[^\)\]\}]*[\)\]\}]\s*", " ", s, flags=re.IGNORECASE)
    # remove trailing descriptors after dashes/pipes
    s = re.sub(r"\s*[-–—|•]\s*\b(live|acoustic|remaster(?:ed)?(?:\s*\d{4})?|demo|session|radio\s*edit|edit|version|mono|stereo|deluxe|extended|re[-\s]?recorded|remix)\b.*$", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[^a-z0-9\s']", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _base_track_key(t: Track) -> str:
    title = _normalize_title(t.name)
    primary_artist = t.artists[0] if t.artists else ""
    artist = str(primary_artist).lower().strip()
    if not title:
        return ""
    return f"{artist}—{title}"


async def get_recommendations(params: dict) -> List[Track]:
    """Build a larger, more diverse pool using multiple batched recommendation calls.

    - Increases per-call limit to 50 (Spotify max is 100) to fetch more at once
    - Performs a few batches with slight jitter on targets to diversify results
    - Dedupe by track ID across batches
    """
    token = get_spotify_app_token()

    import random
    seeds_list = params.get("seed_genres", ["pop"])[:5]

    # Tune these to balance pool size vs. rate limits
    limit = 100  # per request; Spotify allows up to 100
    batches = 4  # number of diversified recommendation pulls

    def jitter(val: Optional[float], amt: float = 0.15, tempo_abs: float = 8.0) -> Optional[float]:
        if val is None:
            return None
        try:
            v = float(val)
            # If looks like tempo (BPM), nudge by absolute amount, clamp to sensible range
            if v > 5:
                j = v + (random.random() * 2 - 1) * tempo_abs
                j = max(40.0, min(220.0, j))
                return round(j, 1)
            # Otherwise treat as ratio in [0,1]
            j = max(0.0, min(1.0, v + (random.random() * 2 - 1) * amt))
            return round(j, 3)
        except Exception:
            return val

    async with httpx.AsyncClient(timeout=10) as client:
        all_items: List[Track] = []
        seen_ids: Set[str] = set()
        last_error = None
        for i in range(batches):
            # Randomize seed selection per batch for variety
            batch_seeds = seeds_list[:]
            random.shuffle(batch_seeds)
            max_take = max(1, min(5, len(batch_seeds)))
            take = random.randint(1, max_take)
            seeds = ",".join(batch_seeds[:take])
            q_params = {
                "limit": limit,
                "seed_genres": seeds,
                "market": SPOTIFY_MARKET,
            }
            # Apply small jitter to diversify between calls
            for k in ("target_tempo", "target_energy", "target_valence", "target_instrumentalness"):
                if k in params:
                    q_params[k] = jitter(params[k], 0.12, 10.0) or params[k]

            # Randomize popularity window to diversify (0-100)
            q_params["min_popularity"] = max(0, min(100, int(random.uniform(5, 70))))
            # Optionally cap max_popularity above min to bias towards mid-long tail sometimes
            q_params["max_popularity"] = max(q_params["min_popularity"] + 10, int(random.uniform(60, 100)))

            r = await client.get(
                "https://api.spotify.com/v1/recommendations",
                params=q_params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                last_error = r
                continue
            data = r.json()
            for t in data.get("tracks", []):
                tid = t.get("id")
                if not tid or tid in seen_ids:
                    continue
                seen_ids.add(tid)
                all_items.append(
                    Track(
                        id=tid,
                        name=t.get("name"),
                        artists=[a.get("name") for a in t.get("artists", [])],
                preview_url=t.get("preview_url"),
                external_url=(t.get("external_urls", {}) or {}).get("spotify"),
                image_url=(t.get("album", {}).get("images", [{}]) or [{}])[0].get("url"),
                duration_ms=t.get("duration_ms"),
            )
        )

    if not all_items:
        # Fallback: try search-based aggregation by seed keywords with larger limit
        tracks_fb = await search_tracks_fallback(seeds_list, token, limit=limit * batches)
        if tracks_fb:
            return tracks_fb
        # Bubble up last error with context
        if last_error is not None:
            try:
                detail = last_error.json()
            except Exception:
                detail = {"status": last_error.status_code, "text": last_error.text[:200]}
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Spotify recommendations failed",
                    "error": detail,
                },
            )
    return all_items


async def search_tracks_fallback(
    seed_genres: List[str],
    token: str,
    limit: int = 20,
    exclude_ids: Optional[Set[str]] = None,
    exclude_keys: Optional[Set[str]] = None,
) -> List[Track]:
    import random
    results: List[Track] = []
    seen: Set[str] = set()
    exclude_ids = exclude_ids or set()
    exclude_keys = exclude_keys or set()
    async with httpx.AsyncClient(timeout=10) as client:
        for seed in seed_genres or ["pop"]:
            # Randomize year window and offset to avoid same results
            start_year = random.randint(1990, 2018)
            end_year = start_year + random.randint(2, 10)
            q = f"{seed} year:{start_year}-{end_year}"
            params = {
                "q": q,
                "type": "track",
                "limit": min(25, limit),
                "offset": random.randint(0, 800),
                "market": SPOTIFY_MARKET,
            }
            resp = await client.get(
                "https://api.spotify.com/v1/search",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for t in (data.get("tracks", {}) or {}).get("items", []):
                tid = t.get("id")
                if not tid or tid in seen or tid in exclude_ids:
                    continue
                # Build Track and compute base key for exclude check
                tr = Track(
                    id=tid,
                    name=t.get("name"),
                    artists=[a.get("name") for a in t.get("artists", [])],
                    preview_url=t.get("preview_url"),
                    external_url=(t.get("external_urls", {}) or {}).get("spotify"),
                    image_url=(t.get("album", {}).get("images", [{}]) or [{}])[0].get("url"),
                    duration_ms=t.get("duration_ms"),
                )
                key = _base_track_key(tr)
                if key and key in exclude_keys:
                    continue
                seen.add(tid)
                results.append(tr)
                if len(results) >= limit:
                    return results
    return results


# -----------------------------------------------------------------------------
# API routes
# -----------------------------------------------------------------------------


@app.post("/api/mood-to-playlist", response_model=PlaylistResponse)
async def mood_to_playlist(body: MoodRequest, db: Session = Depends(get_db)):
    if not body.mood and not body.emoji:
        raise HTTPException(status_code=400, detail="Provide mood or emoji")
    params = mood_to_params(body.mood or "", body.emoji)
    tracks = await get_recommendations(params)

    # Exclude previously seen tracks if client sends them
    exclude_ids = set((body.exclude_ids or []))
    exclude_keys = set((body.exclude_keys or []))
    if exclude_ids or exclude_keys:
        filtered = []
        for t in tracks:
            if t.id in exclude_ids:
                continue
            key = _base_track_key(t)
            if key and key in exclude_keys:
                continue
            filtered.append(t)
        tracks = filtered

    # If filtering removed too many, attempt one more batch to refill.
    # If still too few, allow ignoring excludes to guarantee results.
    if len(tracks) < 20:
        # First refill honoring excludes
        refill = await get_recommendations(params)
        if exclude_ids or exclude_keys:
            tmp = []
            for t in refill:
                if t.id in exclude_ids:
                    continue
                key = _base_track_key(t)
                if key and key in exclude_keys:
                    continue
                tmp.append(t)
            refill = tmp
        # merge while keeping unique by id
        seen = {t.id for t in tracks}
        for t in refill:
            if t.id not in seen:
                tracks.append(t)
                seen.add(t.id)
        # If still too few, do a final refill without excludes
        if len(tracks) < 10:
            # Use search fallback honoring excludes to broaden pool without repeats
            fb = await search_tracks_fallback(
                params.get("seed_genres", ["pop"]),
                get_spotify_app_token(),
                limit=30,
                exclude_ids=exclude_ids,
                exclude_keys=exclude_keys,
            )
            for t in fb:
                if t.id not in seen:
                    tracks.append(t)
                    seen.add(t.id)

    # Optionally persist mood history if user_id provided
    if body.user_id:
        mh = MoodHistory(
            user_id=body.user_id,
            mood_text=body.mood or body.emoji or "",
            params=params,
            tracks=[t.model_dump() for t in tracks],
        )
        db.add(mh)
        db.commit()

    return PlaylistResponse(params=params, tracks=tracks)


@app.get("/api/moods/history", response_model=List[HistoryItem])
def get_history(user_id: int, db: Session = Depends(get_db)):
    q = db.query(MoodHistory).filter(MoodHistory.user_id == user_id).order_by(MoodHistory.created_at.desc()).limit(50)
    items = [
        HistoryItem(
            id=m.id,
            mood_text=m.mood_text,
            params=m.params,
            tracks=m.tracks,
            created_at=str(m.created_at) if m.created_at else None,
        )
        for m in q.all()
    ]
    return items


@app.post("/api/save-playlist")
def save_playlist(req: SavePlaylistRequest, db: Session = Depends(get_db)):
    # Requires user to be authenticated with Spotify and refresh_token stored
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user or not user.refresh_token:
        raise HTTPException(status_code=401, detail="User not linked to Spotify")

    # Refresh access token
    token_resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": user.refresh_token,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        },
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to refresh token")
    access_token = token_resp.json().get("access_token")

    # Get current user's profile to ensure we have spotify_user_id
    if not user.spotify_user_id:
        me = requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        ).json()
        user.spotify_user_id = me.get("id")
        user.display_name = me.get("display_name")
        db.add(user)
        db.commit()

    # Create a playlist
    pl_resp = requests.post(
        f"https://api.spotify.com/v1/users/{user.spotify_user_id}/playlists",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        data=orjson.dumps({"name": req.name, "public": False}).decode(),
        timeout=10,
    )
    if pl_resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Failed to create playlist")
    playlist_id = pl_resp.json().get("id")

    # Add tracks to the playlist
    uris = [f"spotify:track:{tid}" for tid in req.track_ids]
    add_resp = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        data=orjson.dumps({"uris": uris}).decode(),
        timeout=10,
    )
    if add_resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Failed to add tracks")

    return {"playlist_id": playlist_id}


# -----------------------------------------------------------------------------
# Spotify OAuth (Authorization Code) endpoints
# -----------------------------------------------------------------------------


@app.get("/api/auth/login")
def spotify_login(redirect: bool = False):
    scopes = [
        "playlist-modify-private",
        "playlist-modify-public",
        "user-read-email",
        "user-read-private",
    ]
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(scopes),
        "show_dialog": "false",
    }
    base = "https://accounts.spotify.com/authorize"
    from urllib.parse import urlencode

    auth_url = f"{base}?{urlencode(params)}"
    if redirect:
        return RedirectResponse(url=auth_url, status_code=302)
    return {"auth_url": auth_url}


class OAuthCallback(BaseModel):
    code: str


@app.get("/api/auth/callback")
def spotify_callback(code: str, db: Session = Depends(get_db)):
    token_resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")
    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    me = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    ).json()

    spotify_user_id = me.get("id")
    display_name = me.get("display_name")

    # Upsert user
    with db.begin():
        user = db.query(User).filter(User.spotify_user_id == spotify_user_id).first()
        if user:
            user.refresh_token = refresh_token or user.refresh_token
            user.display_name = display_name
        else:
            user = User(spotify_user_id=spotify_user_id, display_name=display_name, refresh_token=refresh_token)
            db.add(user)

    # Redirect back to frontend with user info for dev UX
    try:
        dest = f"{FRONTEND_ORIGIN}/?user_id={user.id}&display_name={requests.utils.requote_uri(user.display_name or '')}"
        return RedirectResponse(url=dest, status_code=302)
    except Exception:
        # Fallback to JSON
        return {"user_id": user.id, "display_name": user.display_name}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/spotify/genres")
def available_genres():
    seeds = sorted(list(get_available_genre_seeds()))
    return {"genres": seeds}


@app.get("/api/debug/config")
def debug_config():
    # Do NOT return secrets; just booleans and important settings
    try:
        seeds = list(get_available_genre_seeds())
        seeds_count = len(seeds)
    except Exception:
        seeds_count = -1
    sample_params = mood_to_params("focus")
    return {
        "has_client_id": bool(SPOTIFY_CLIENT_ID),
        "has_client_secret": bool(SPOTIFY_CLIENT_SECRET),
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "market": SPOTIFY_MARKET,
        "available_genres_count": seeds_count,
        "sample_params_for_focus": sample_params,
    }


@app.get("/api/debug/spotify")
def debug_spotify():
    token = get_spotify_app_token()
    # Check available seeds
    seeds_status = None
    try:
        resp = requests.get(
            "https://api.spotify.com/v1/recommendations/available-genre-seeds",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        seeds_status = {"status": resp.status_code, "ok": resp.status_code == 200, "len": len((resp.json() or {}).get("genres", [])) if resp.status_code == 200 else None}
    except Exception as e:
        seeds_status = {"status": "error", "error": str(e)}

    # Check recommendations with known seed
    try:
        r = requests.get(
            "https://api.spotify.com/v1/recommendations",
            params={"limit": 1, "seed_genres": "pop", "market": SPOTIFY_MARKET},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text[:200]}
        rec_status = {"status": r.status_code, "ok": r.status_code == 200, "tracks": len(body.get("tracks", [])) if r.status_code == 200 else None, "body": body}
    except Exception as e:
        rec_status = {"status": "error", "error": str(e)}

    return {"seeds": seeds_status, "recommendations": rec_status}


# -----------------------------------------------------------------------------
# Run with: uvicorn backend.main:app --reload --port 8000
# -----------------------------------------------------------------------------
