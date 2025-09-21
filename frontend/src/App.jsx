import React, { useEffect, useMemo, useRef, useState } from 'react'
import Waveform from './components/Waveform'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const EMOJIS = ['😊', '😢', '😤', '❤️', '🧘', '🏋️']

export default function App() {
  const [mood, setMood] = useState('')
  const [emoji, setEmoji] = useState('')
  const [loading, setLoading] = useState(false)
  const [playlist, setPlaylist] = useState(null)
  const [user, setUser] = useState(null)
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef(null)

  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition
      const rec = new SR()
      rec.lang = 'en-US'
      rec.continuous = false
      rec.interimResults = false
      rec.onresult = (e) => {
        const t = e.results?.[0]?.[0]?.transcript
        if (t) setMood(t)
        setListening(false)
      }
      rec.onerror = () => setListening(false)
      rec.onend = () => setListening(false)
      recognitionRef.current = rec
    }
  }, [])

  const startListening = () => {
    if (!recognitionRef.current) return alert('Speech recognition not supported in this browser.')
    setListening(true)
    recognitionRef.current.start()
  }

  const fetchPlaylist = async (e) => {
    e?.preventDefault()
    setLoading(true)
    setPlaylist(null)
    try {
      const res = await fetch(`${API_BASE}/api/mood-to-playlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mood, emoji, user_id: user?.id }),
      })
      if (!res.ok) throw new Error('Failed to fetch playlist')
      const data = await res.json()
      setPlaylist(data)
    } catch (err) {
      console.error(err)
      alert('Could not generate playlist.')
    } finally {
      setLoading(false)
    }
  }

  const loginSpotify = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`)
      const data = await res.json()
      window.location.href = data.auth_url
    } catch (e) {
      alert('Failed to start Spotify login')
    }
  }

  // Parse callback code from URL and exchange for user
  useEffect(() => {
    const url = new URL(window.location.href)
    const code = url.searchParams.get('code')
    if (code) {
      ;(async () => {
        const res = await fetch(`${API_BASE}/api/auth/callback?code=${encodeURIComponent(code)}`)
        if (res.ok) {
          const u = await res.json()
          setUser(u)
          // Clear the code from URL
          url.searchParams.delete('code')
          window.history.replaceState({}, '', url.toString())
        }
      })()
    }
  }, [])

  const savePlaylist = async () => {
    if (!user) return alert('Log in with Spotify first')
    if (!playlist) return
    const name = prompt('Playlist name?', `Melo • ${mood || emoji || 'My Mood'}`)
    if (!name) return
    try {
      const trackIds = (playlist.tracks || []).map((t) => t.id)
      const res = await fetch(`${API_BASE}/api/save-playlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id || user.id, name, track_ids: trackIds }),
      })
      if (!res.ok) throw new Error('Save failed')
      const data = await res.json()
      alert(`Saved playlist! ID: ${data.playlist_id}`)
    } catch (e) {
      alert('Could not save playlist')
    }
  }

  return (
    <div className="melo-gradient min-h-screen">
      <div className="max-w-3xl mx-auto px-6 py-10">
        <header className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-semibold">Melo</h1>
          <div className="flex items-center gap-3">
            {user ? (
              <span className="text-sm text-gray-300">Signed in</span>
            ) : (
              <button onClick={loginSpotify} className="px-3 py-2 bg-green-600 hover:bg-green-500 rounded text-sm">Connect Spotify</button>
            )}
          </div>
        </header>

        <form onSubmit={fetchPlaylist} className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
          <label className="block text-sm text-gray-300">How are you feeling?</label>
          <input
            value={mood}
            onChange={(e) => setMood(e.target.value)}
            placeholder="e.g., focus, chill, happy..."
            className="w-full rounded bg-white/10 border border-white/10 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-400"
          />
          <div className="flex items-center gap-2">
            {EMOJIS.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => setEmoji(e)}
                className={`text-2xl px-2 py-1 rounded ${emoji === e ? 'bg-white/20' : 'hover:bg-white/10'}`}
                aria-label={`Select ${e}`}
              >{e}</button>
            ))}
            <button
              type="button"
              onClick={startListening}
              className={`ml-auto px-3 py-2 rounded border border-white/10 ${listening ? 'bg-red-600' : 'bg-white/10 hover:bg-white/20'}`}
            >{listening ? 'Listening...' : '🎙️ Record'}</button>
          </div>
          <div className="flex gap-2">
            <button disabled={loading} className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded disabled:opacity-50">Generate Playlist</button>
            {playlist && (
              <button type="button" onClick={savePlaylist} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded">Save</button>
            )}
          </div>
        </form>

        <div className="mt-10">
          <Waveform active={loading} />
        </div>

        {playlist && (
          <section className="mt-8">
            <h2 className="text-xl font-semibold mb-3">Your Playlist</h2>
            <p className="text-sm text-gray-400 mb-4">Params: {JSON.stringify(playlist.params)}</p>
            <ul className="grid md:grid-cols-2 gap-4">
              {playlist.tracks.map((t) => (
                <li key={t.id} className="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div className="flex items-center gap-4">
                    {t.image_url && (
                      <img src={t.image_url} alt="album art" className="w-16 h-16 object-cover rounded" />
                    )}
                    <div className="flex-1">
                      <div className="font-medium">{t.name}</div>
                      <div className="text-sm text-gray-400">{t.artists.join(', ')}</div>
                      {t.preview_url ? (
                        <audio controls src={t.preview_url} className="mt-2 w-full" />
                      ) : (
                        <div className="text-xs text-gray-500 mt-2">No preview available</div>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

      </div>
    </div>
  )
}

