import os
import time
from typing import List, Optional

import httpx
import orjson
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


# Load environment variables from .env if present
load_dotenv()

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
POSTGRES_URL = os.getenv("POSTGRES_URL", "sqlite:///./melo.db")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")


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
    created_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    moods: Mapped[List["MoodHistory"]] = relationship(back_populates="user")


class MoodHistory(Base):
    __tablename__ = "mood_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mood_text: Mapped[str] = mapped_column(String(500))
    params: Mapped[dict] = mapped_column(JSON)
    tracks: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), server_default=func.now())
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


class Track(BaseModel):
    id: str
    name: str
    artists: List[str]
    preview_url: Optional[str] = None
    external_url: Optional[str] = None
    image_url: Optional[str] = None


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
        ("chill", {"seed_genres": ["chill", "lo-fi"], "target_tempo": 85, "target_energy": 0.4, "target_valence": 0.6}),
        ("lofi", {"seed_genres": ["lo-fi"], "target_tempo": 75, "target_energy": 0.3}),
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
    return params


async def get_recommendations(params: dict) -> List[Track]:
    token = get_spotify_app_token()
    seeds = ",".join(params.get("seed_genres", ["pop"])[:5])
    q_params = {
        "limit": 20,
        "seed_genres": seeds,
    }
    for k in ("target_tempo", "target_energy", "target_valence", "target_instrumentalness"):
        if k in params:
            q_params[k] = params[k]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.spotify.com/v1/recommendations",
            params=q_params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Spotify recommendations failed")
    data = r.json()
    items = []
    for t in data.get("tracks", []):
        items.append(
            Track(
                id=t["id"],
                name=t["name"],
                artists=[a["name"] for a in t.get("artists", [])],
                preview_url=t.get("preview_url"),
                external_url=(t.get("external_urls", {}) or {}).get("spotify"),
                image_url=(t.get("album", {}).get("images", [{}]) or [{}])[0].get("url"),
            )
        )
    return items


# -----------------------------------------------------------------------------
# API routes
# -----------------------------------------------------------------------------


@app.post("/api/mood-to-playlist", response_model=PlaylistResponse)
async def mood_to_playlist(body: MoodRequest, db: Session = Depends(get_db)):
    if not body.mood and not body.emoji:
        raise HTTPException(status_code=400, detail="Provide mood or emoji")
    params = mood_to_params(body.mood or "", body.emoji)
    tracks = await get_recommendations(params)

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
def spotify_login():
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

    return {"auth_url": f"{base}?{urlencode(params)}"}


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

    return {"user_id": user.id, "display_name": user.display_name}


@app.get("/api/health")
def health():
    return {"ok": True}


# -----------------------------------------------------------------------------
# Run with: uvicorn backend.main:app --reload --port 8000
# -----------------------------------------------------------------------------
