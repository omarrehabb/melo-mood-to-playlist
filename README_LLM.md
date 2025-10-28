# LLM-Powered Vibe Parsing

This backend extension adds an LLM-powered phrase parser that converts free-form descriptions into structured Spotify recommendation parameters while keeping the original single-word mood flow intact.

## Environment

Set the following variables (e.g. in `backend/.env`):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini  # optional override
```

Existing Spotify credentials continue to apply (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, etc.).

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

## Endpoint

`POST /api/vibe`

Request body:

```json
{
  "phrase": "romantic date in paris at sunset"
}
```

Response outline:

```json
{
  "source": "llm",
  "slots": { ... },
  "targets": { ... },
  "seed_genres": [ ... ],
  "tracks": [ ... ]
}
```

When the LLM returns low confidence or the schema fails validation, the handler automatically falls back to the legacy single-word mood mapping.

## Example

```bash
curl -X POST http://localhost:8000/api/vibe \
  -H "Content-Type: application/json" \
  -d '{"phrase":"late night coding, no lyrics"}'
```

The response includes the extracted slots, the derived Spotify features (`target_*` fields) and up to five seed genres, together with curated tracks.

## Testing

Run the new unit suite:

```bash
pytest backend/tests
```
