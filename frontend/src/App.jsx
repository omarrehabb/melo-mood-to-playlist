import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { CssBaseline, Box, Container, Typography, TextField, Button, IconButton, Avatar, Divider, Grid, Tooltip } from '@mui/material'
import { Settings, Send, DarkMode, LightMode } from '@mui/icons-material'
import { SiSpotify } from 'react-icons/si'
import LoadingOverlay from './components/LoadingOverlay'
import SongCard from './components/SongCard'
import theme, { makeTheme } from './theme'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

const MOOD_EMOJIS = [
  { emoji: '😄', label: 'Happy' },
  { emoji: '😢', label: 'Sad' },
  { emoji: '⚡️', label: 'Energetic' },
  { emoji: '😌', label: 'Relaxed' },
  { emoji: '😠', label: 'Angry' },
  { emoji: '🧘', label: 'Calm' },
]

export default function App() {
  const [mood, setMood] = useState('')
  const [selectedEmoji, setSelectedEmoji] = useState('')
  const [loading, setLoading] = useState(false)
  const [playlist, setPlaylist] = useState(null)
  const [user, setUser] = useState(null)
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef(null)
  const [darkMode, setDarkMode] = useState(true)

  // initialize theme mode from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('melo_theme')
      if (saved === 'light') setDarkMode(false)
    } catch {}
  }, [])

  // reflect mode to <html> class for Tailwind dark: styles
  useEffect(() => {
    const root = document.documentElement
    if (darkMode) root.classList.add('dark')
    else root.classList.remove('dark')
    try { localStorage.setItem('melo_theme', darkMode ? 'dark' : 'light') } catch {}
  }, [darkMode])

  const muiTheme = useMemo(() => makeTheme(darkMode ? 'dark' : 'light'), [darkMode])

  // Persistent per-mood dedupe to avoid repeats across runs (v2 schema)
  const MOOD_SEEN_STORAGE_KEY = 'melo_seen_tracks_v2'
  const moodKey = useMemo(() => {
    const m = (mood || '').trim().toLowerCase()
    const e = (selectedEmoji || '').trim()
    return `${m}__${e}`
  }, [mood, selectedEmoji])

  const loadSeenForMood = (key) => {
    try {
      const raw = localStorage.getItem(MOOD_SEEN_STORAGE_KEY)
      if (!raw) return { keys: new Set(), ids: new Set() }
      const obj = JSON.parse(raw) || {}
      const entry = obj[key]
      if (Array.isArray(entry)) {
        // backward-compat for v1 (keys only)
        return { keys: new Set(entry), ids: new Set() }
      }
      return {
        keys: new Set(Array.isArray(entry?.keys) ? entry.keys : []),
        ids: new Set(Array.isArray(entry?.ids) ? entry.ids : []),
      }
    } catch {
      return { keys: new Set(), ids: new Set() }
    }
  }

  const saveSeenForMood = (key, seen) => {
    try {
      const raw = localStorage.getItem(MOOD_SEEN_STORAGE_KEY)
      const obj = raw ? (JSON.parse(raw) || {}) : {}
      const keysList = Array.from(seen.keys)
      const idsList = Array.from(seen.ids)
      obj[key] = { keys: keysList.slice(-800), ids: idsList.slice(-800) }
      localStorage.setItem(MOOD_SEEN_STORAGE_KEY, JSON.stringify(obj))
    } catch {}
  }

  // Helpers to normalize titles and dedupe similar versions (live, remaster, acoustic, edits, etc.)
  const normalizeTitle = (raw) => {
    if (!raw) return ''
    let s = String(raw).toLowerCase()
    // remove featuring/with credits from title
    s = s.replace(/\s*(\(|-|–|—)?\s*(feat\.|featuring|with)\s+[^)\-–—]+\)?/gi, '')
    // remove bracketed descriptors with common version keywords
    s = s.replace(/\s*[\(\[\{][^\)\]\}]*\b(live|acoustic|remaster(?:ed)?(?:\s*\d{4})?|demo|session|radio\s*edit|edit|version|mono|stereo|deluxe|extended|re[-\s]?recorded|remix)\b[^\)\]\}]*[\)\]\}]\s*/gi, ' ')
    // remove dash/pipe separated descriptors at end
    s = s.replace(/\s*[-–—|•]\s*\b(live|acoustic|remaster(?:ed)?(?:\s*\d{4})?|demo|session|radio\s*edit|edit|version|mono|stereo|deluxe|extended|re[-\s]?recorded|remix)\b.*$/gi, ' ')
    // collapse whitespace and trim punctuation
    s = s.replace(/[^a-z0-9\s']/g, ' ').replace(/\s{2,}/g, ' ').trim()
    return s
  }

  const baseTrackKey = (t) => {
    const title = normalizeTitle(t?.name || '')
    const primaryArtist = (Array.isArray(t?.artists) ? t.artists[0] : t?.artists) || ''
    const artist = String(primaryArtist).toLowerCase().trim()
    if (!title) return ''
    return `${artist}—${title}`
  }

  // Deduplicate tracks for display by normalized title + primary artist
  const filteredTracks = useMemo(() => {
    const seen = new Set()
    const list = []
    for (const t of playlist?.tracks || []) {
      const key = baseTrackKey(t)
      if (!key || seen.has(key)) continue
      seen.add(key)
      list.push(t)
    }
    return list
  }, [playlist])

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
      // First call (records history if user present) and sends exclude sets
      const res = await fetch(`${API_BASE}/api/mood-to-playlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mood,
          emoji: selectedEmoji,
          user_id: user?.user_id || user?.id,
          // Provide excludes so backend can avoid repeats across runs (limit to avoid over-filtering)
          exclude_ids: Array.from(loadSeenForMood(moodKey).ids).slice(-300),
          exclude_keys: Array.from(loadSeenForMood(moodKey).keys).slice(-300),
        }),
      })
      if (!res.ok) throw new Error('Failed to fetch playlist')
      const data = await res.json()

      // Backend now returns a larger diversified pool; no need for extra calls
      const combinedTracks = [...(data.tracks || [])]

      // From the returned tracks, build a larger randomized, de-duplicated set
      // 1) de-dup similar versions by base key
      const uniq = []
      const seenBaseLocal = new Set()
      for (const t of combinedTracks || []) {
        const k = baseTrackKey(t)
        if (!k || seenBaseLocal.has(k)) continue
        seenBaseLocal.add(k)
        uniq.push(t)
      }
      // 2) shuffle
      for (let i = uniq.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[uniq[i], uniq[j]] = [uniq[j], uniq[i]]
      }
      // 3) prefer tracks not seen before for this mood
      const seenForMood = loadSeenForMood(moodKey)
      const fresh = uniq.filter((t) => !seenForMood.keys.has(baseTrackKey(t)) && !seenForMood.ids.has(t.id))
      let finalTracks = fresh.length ? fresh : uniq

      // If still empty (over-filtered or backend filtered too much), retry without excludes
      if (finalTracks.length === 0) {
        const res2 = await fetch(`${API_BASE}/api/mood-to-playlist`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mood, emoji: selectedEmoji, user_id: user?.user_id || user?.id }),
        })
        if (res2.ok) {
          const data2 = await res2.json()
          const uniq2 = []
          const seen2 = new Set()
          for (const t of data2.tracks || []) {
            const k2 = baseTrackKey(t)
            if (!k2 || seen2.has(k2)) continue
            seen2.add(k2)
            uniq2.push(t)
          }
          // shuffle
          for (let i = uniq2.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1))
            ;[uniq2[i], uniq2[j]] = [uniq2[j], uniq2[i]]
          }
          finalTracks = uniq2
        }
      }

      // Update seen registry with what we are about to show
      for (const t of finalTracks) {
        const k = baseTrackKey(t)
        if (k) seenForMood.keys.add(k)
        if (t.id) seenForMood.ids.add(t.id)
      }
      saveSeenForMood(moodKey, seenForMood)

      setPlaylist({ ...data, tracks: finalTracks })
    } catch (err) {
      console.error(err)
      alert('Could not generate playlist.')
    } finally {
      setLoading(false)
    }
  }

  const loginSpotify = () => {
    // Simpler and more reliable: have the backend redirect directly
    window.location.assign(`${API_BASE}/api/auth/login?redirect=1`)
  }

  // Load user from localStorage on first mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem('melo_user')
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && parsed.user_id) setUser(parsed)
      }
    } catch {}
  }, [])

  // Parse user from query after backend redirect, or handle code (legacy)
  useEffect(() => {
    const url = new URL(window.location.href)
    const uid = url.searchParams.get('user_id')
    const display = url.searchParams.get('display_name')
    if (uid) {
      const u = { user_id: Number(uid), display_name: display || '' }
      setUser(u)
      try { localStorage.setItem('melo_user', JSON.stringify(u)) } catch {}
      url.searchParams.delete('user_id')
      url.searchParams.delete('display_name')
      window.history.replaceState({}, '', url.toString())
      return
    }
    const code = url.searchParams.get('code')
    if (code) {
      ;(async () => {
        const res = await fetch(`${API_BASE}/api/auth/callback?code=${encodeURIComponent(code)}`)
        if (res.ok) {
          const u = await res.json()
          setUser(u)
          try { localStorage.setItem('melo_user', JSON.stringify(u)) } catch {}
        }
        url.searchParams.delete('code')
        window.history.replaceState({}, '', url.toString())
      })()
    }
  }, [])

  const savePlaylist = async () => {
    if (!user) return alert('Log in with Spotify first')
    if (!playlist) return
    const name = prompt('Playlist name?', `Melo • ${mood || selectedEmoji || 'My Mood'}`)
    if (!name) return
    try {
      // Ensure we don't save duplicate songs (by normalized base title + primary artist)
      const uniqueByBase = []
      const seenBase = new Set()
      for (const t of playlist.tracks || []) {
        const key = baseTrackKey(t)
        if (!key || seenBase.has(key)) continue
        seenBase.add(key)
        uniqueByBase.push(t)
      }
      // Also guard against duplicate IDs just in case
      const trackIds = Array.from(new Set(uniqueByBase.map((t) => t.id)))
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

  // Derive Spotify avatar and fallback initials
  const getInitials = (name) => {
    if (!name || typeof name !== 'string') return 'U'
    const parts = name.trim().split(/\s+/)
    const letters = parts.slice(0, 2).map((p) => p[0]).join('')
    return (letters || name[0] || 'U').toUpperCase()
  }

  const EqualizerBar = ({ delay = 0, opacity = 1 }) => (
    <div
      className={`h-2 w-1 bg-accent-green equalizer-bar`}
      style={{
        animationDelay: `${delay}s`,
        opacity: opacity,
      }}
    />
  )


  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box
        className="relative flex h-auto min-h-screen w-full flex-col overflow-x-hidden"
        sx={{ backgroundColor: 'background.default', color: 'text.primary' }}
      >
        <Box className="layout-container flex h-full grow flex-col">
          {/* Header */}
          <Box className="flex items-center justify-between whitespace-nowrap px-6 sm:px-10 py-4" sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Box className="flex items-center gap-3">
              <svg className="size-6" fill="none" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" style={{ color: muiTheme.palette.secondary.main }}>
                <path clipRule="evenodd" d="M24 0.757355L47.2426 24L24 47.2426L0.757355 24L24 0.757355ZM21 35.7574V12.2426L9.24264 24L21 35.7574Z" fill="currentColor" fillRule="evenodd"></path>
              </svg>
              <Typography variant="h2" className="text-xl font-bold" color="text.primary">Melo</Typography>
            </Box>
            <Box className="flex items-center gap-4">
              <IconButton className="group flex items-center justify-center rounded-full size-10 bg-accent-green/10 hover:bg-accent-green/20 transition-colors">
                <Settings sx={{ color: 'text.primary' }} />
              </IconButton>
              <Tooltip title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}>
                <IconButton
                  onClick={() => setDarkMode((v) => !v)}
                  className="group flex items-center justify-center rounded-full size-10 bg-accent-green/10 hover:bg-accent-green/20 transition-colors"
                >
                  {darkMode ? <LightMode sx={{ color: 'text.primary' }} /> : <DarkMode sx={{ color: 'text.primary' }} />}
                </IconButton>
              </Tooltip>
              <Avatar
                className="size-10 rounded-full bg-cover bg-center"
                src={user?.images?.[0]?.url || null}
                alt={user?.display_name || 'User'}
              >
                {getInitials(user?.display_name || '')}
              </Avatar>
            </Box>
          </Box>

          {/* Main Content */}
          <Box component="main" className="flex flex-1 flex-col items-center px-4 py-8 sm:px-6">
            <Container maxWidth="sm" className="w-full space-y-8">
              <Box className="text-center">
                <Typography
                  variant="h1"
                  className="text-3xl sm:text-4xl font-bold"
                  color="text.primary"
                >
                  How are you feeling?
                </Typography>
              </Box>

              {/* Mood Input */}
              <Box className="relative">
                <TextField
                  fullWidth
                  value={mood}
                  onChange={(e) => setMood(e.target.value)}
                  placeholder="Describe your mood, e.g. 'upbeat and focused'"
                  variant="outlined"
                  className="w-full"
                  sx={(theme) => ({
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      paddingRight: '60px',
                      backgroundColor: theme.palette.mode === 'dark' ? 'rgba(245,247,248,0.05)' : 'rgba(0,0,0,0.03)',
                      '& fieldset': { borderColor: theme.palette.divider },
                      '&:hover fieldset': { borderColor: theme.palette.secondary.main },
                      '&.Mui-focused fieldset': {
                        borderColor: theme.palette.secondary.main,
                        boxShadow: theme.palette.mode === 'dark' ? '0 0 15px rgba(46,255,199,0.2)' : '0 0 0 rgba(0,0,0,0)'
                      },
                    },
                    '& .MuiInputBase-input': {
                      color: theme.palette.text.primary,
                      paddingRight: '60px',
                      '&::placeholder': {
                        color: theme.palette.text.secondary,
                        opacity: 1,
                      },
                    },
                  })}
                />
                <IconButton
                  onClick={fetchPlaylist}
                  disabled={loading}
                  sx={{
                    position: 'absolute',
                    right: '8px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '48px',
                    height: '48px',
                    borderRadius: '50%',
                    backgroundColor: 'rgba(53, 158, 255, 0.2)',
                    '&:hover': {
                      backgroundColor: 'rgba(53, 158, 255, 0.3)',
                    },
                    '&:disabled': {
                      opacity: 0.5,
                    },
                  }}
                >
                  <Send sx={{ color: (theme) => theme.palette.text.secondary, fontSize: '20px' }} />
                </IconButton>
              </Box>

              {/* Divider */}
              <Box className="flex items-center gap-4">
                <Box className="h-px flex-1" sx={{ backgroundColor: 'divider' }}></Box>
                <Typography className="text-sm font-medium" color="text.secondary">OR</Typography>
                <Box className="h-px flex-1" sx={{ backgroundColor: 'divider' }}></Box>
              </Box>

              {/* Emoji Buttons */}
              <Box className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {MOOD_EMOJIS.map(({ emoji, label }) => {
                  const isSelected = selectedEmoji === emoji
                  return (
                    <Button
                      key={emoji}
                      fullWidth
                      variant="contained"
                      disableElevation
                      onClick={() => {
                        const next = isSelected ? '' : emoji
                        setSelectedEmoji(next)
                        if (next) setMood(label)
                      }}
                      className="group relative flex flex-col items-center justify-center gap-2 overflow-hidden text-white"
                      sx={{
                        // Half the previous size
                        minHeight: { xs: 60, sm: 72 },
                        flexDirection: 'column',
                        gap: 1,
                        borderRadius: '32px',
                        padding: { xs: '12px 10px', sm: '14px 12px' },
                        alignSelf: 'stretch',
                        // Remove aspect ratio so height stays compact
                        aspectRatio: 'auto',
                        textTransform: 'none',
                        background: isSelected
                          ? 'linear-gradient(160deg, rgba(13, 36, 58, 0.96), rgba(15, 58, 84, 0.96))'
                          : 'linear-gradient(155deg, rgba(8, 21, 36, 0.95), rgba(6, 16, 28, 0.95))',
                        border: isSelected
                          ? '1px solid rgba(46, 255, 199, 0.45)'
                          : '1px solid rgba(255, 255, 255, 0.08)',
                        boxShadow: isSelected
                          ? '0 28px 60px -18px rgba(46, 255, 199, 0.45), 0 18px 38px -16px rgba(9, 27, 44, 0.85)'
                          : '0 22px 48px -22px rgba(6, 12, 24, 0.9)',
                        transform: isSelected ? 'translateY(-6px)' : 'translateY(0)',
                        transition: 'all 0.35s ease',
                        '&:hover': {
                          background: 'linear-gradient(160deg, rgba(12, 31, 53, 0.98), rgba(9, 27, 44, 0.95))',
                          boxShadow: isSelected
                            ? '0 32px 66px -18px rgba(46, 255, 199, 0.55), 0 20px 40px -16px rgba(9, 27, 44, 0.85)'
                            : '0 28px 60px -20px rgba(46, 255, 199, 0.35)',
                          borderColor: 'rgba(46, 255, 199, 0.32)',
                          transform: 'translateY(-6px)',
                        },
                        '& .MuiTypography-root': {
                          color: '#ffffff',
                        },
                      }}
                    >
                      <span className="pointer-events-none absolute inset-0 z-0 rounded-[32px] bg-gradient-to-br from-white/10 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-40" />
                      <span
                        className={`pointer-events-none absolute inset-[6%] z-0 rounded-[28px] bg-[radial-gradient(circle_at_20%_20%,_rgba(46,255,199,0.22),_transparent_60%)] transition-opacity duration-500 ${
                          isSelected ? 'opacity-100' : 'opacity-60 group-hover:opacity-80'
                        }`}
                      />
                      <Typography
                        component="div"
                        className="relative z-10 drop-shadow-[0_6px_18px_rgba(0,0,0,0.55)]"
                        sx={{
                          // Half of previous emoji size
                          fontSize: { xs: '1.5rem', sm: '2.0625rem', md: '2.625rem' },
                          lineHeight: 1,
                          textAlign: 'center',
                        }}
                      >
                        {emoji}
                      </Typography>
                      <Typography className="relative z-10 text-2xl font-semibold tracking-wide">
                        {label}
                      </Typography>
                    </Button>
                  )
                })}
              </Box>

              {/* Action Buttons */}
              <Box className="space-y-4 pt-4">
                <Button
                  fullWidth
                  variant="contained"
                  onClick={fetchPlaylist}
                  disabled={loading}
                  className="w-full rounded-xl py-4 text-center font-bold transition-transform hover:scale-105 shadow-[0_0_25px_rgba(46,255,199,0.4)]"
                  sx={{
                    backgroundColor: '#1DB954',
                    color: '#ffffff',
                    '&:hover': {
                      backgroundColor: '#19a34d',
                    },
                  }}
                >
                  Generate Playlist
                </Button>

                <Button
                  fullWidth
                  variant="outlined"
                  onClick={loginSpotify}
                  className="group flex w-full items-center justify-center gap-2 rounded-xl border-2 border-green-500/50 bg-transparent py-3 text-center font-semibold text-green-400 transition-colors hover:bg-green-500/20 hover:text-green-300"
                  sx={{
                    borderColor: 'rgba(34, 197, 94, 0.5)',
                    color: '#4ade80',
                    '&:hover': {
                      backgroundColor: 'rgba(34, 197, 94, 0.2)',
                      color: '#22c55e',
                    },
                  }}
                  disabled={!!user}
                >
                  <SiSpotify size={20} color="#1DB954" />
                  <span>{user ? `Connected as ${user.display_name || 'User'}` : 'Connect to Spotify'}</span>
                </Button>
              </Box>
            </Container>
          </Box>

          {/* Footer with Equalizer (hidden during loading) */}
          {!loading && (
            <Box component="footer" className="mt-auto px-4 pb-4">
              <Box className="flex items-center justify-center h-16 w-full max-w-lg mx-auto">
                <Box className="flex items-center justify-around w-full h-full">
                  <EqualizerBar delay={0.1} opacity={0.7} />
                  <EqualizerBar delay={0.2} opacity={1} />
                  <EqualizerBar delay={0.3} opacity={0.7} />
                  <EqualizerBar delay={0.4} opacity={1} />
                  <EqualizerBar delay={0.5} opacity={0.7} />
                  <EqualizerBar delay={0.6} opacity={1} />
                  <EqualizerBar delay={0.7} opacity={0.7} />
                  <EqualizerBar delay={0.8} opacity={1} />
                  <EqualizerBar delay={0.9} opacity={0.7} className="hidden sm:block" />
                  <EqualizerBar delay={1.0} opacity={1} className="hidden sm:block" />
                  <EqualizerBar delay={1.1} opacity={0.7} className="hidden sm:block" />
                  <EqualizerBar delay={1.2} opacity={1} className="hidden sm:block" />
                </Box>
              </Box>
            </Box>
          )}
        </Box>

        {/* Loading Overlay */}
        {loading && <LoadingOverlay text="Generating your playlist…" />}

        {/* Playlist Results */}
        {playlist && (
          <Box className="mt-8 px-4">
            <Container maxWidth="lg">
              <Typography variant="h2" className="text-xl font-semibold mb-8 text-white">
                Your Playlist
              </Typography>
              {/* Removed params display */}
              <Grid container spacing={3} alignItems="stretch">
                {filteredTracks.map((t) => (
                  <Grid item xs={12} sm={6} md={3} lg={3} key={t.id}>
                    <SongCard track={t} />
                  </Grid>
                ))}
              </Grid>
              <Box className="mt-8">
                <Button
                  fullWidth
                  size="large"
                  variant="contained"
                  onClick={savePlaylist}
                  className="w-full rounded-xl py-4 text-lg font-bold transition-transform hover:scale-105 shadow-[0_0_25px_rgba(46,255,199,0.4)]"
                  sx={{
                    backgroundColor: '#1DB954',
                    color: '#ffffff',
                    '&:hover': {
                      backgroundColor: '#19a34d',
                    },
                  }}
                >
                  Save Playlist
                </Button>
              </Box>
            </Container>
          </Box>
        )}
      </Box>
    </ThemeProvider>
  )
}
