Melo — Mood to Spotify Playlist

Quickstart for a minimal full‑stack app:

Backend (FastAPI)
- Files: backend/main.py, backend/requirements.txt
- Env vars (create .env in backend/):
  - SPOTIFY_CLIENT_ID=your_client_id
  - SPOTIFY_CLIENT_SECRET=your_client_secret
  - SPOTIFY_REDIRECT_URI=http://localhost:8000/api/auth/callback
  - POSTGRES_URL=postgresql+psycopg2://user:pass@localhost:5432/melo (defaults to sqlite file if not set)
  - FRONTEND_ORIGIN=http://localhost:5173

Run backend:
- python -m venv .venv && source .venv/bin/activate
- pip install -r backend/requirements.txt
- uvicorn backend.main:app --reload --port 8000

Frontend (React + Tailwind via Vite)
- Files under frontend/
- Optional: set VITE_API_BASE in frontend (defaults to http://localhost:8000)

Run frontend:
- cd frontend
- npm install
- npm run dev

Endpoints
- POST /api/mood-to-playlist → { mood, emoji, user_id? } → Spotify recommendations
- POST /api/save-playlist → { user_id, name, track_ids[] } → saves to user’s Spotify
- GET  /api/moods/history?user_id=... → recent moods and tracks
- GET  /api/auth/login → returns Spotify auth_url
- GET  /api/auth/callback?code=... → exchanges code; upserts user; returns { user_id }

Notes
- Uses simple keyword/emoji rules to map mood to Spotify recommendation parameters (genre, tempo, energy, valence, instrumentalness).
- Uses Client Credentials for recommendations; Authorization Code + refresh tokens for saving playlists.
- DB defaults to SQLite for easy start; switch POSTGRES_URL to PostgreSQL in prod.

