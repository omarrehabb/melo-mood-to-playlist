import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ThemeProvider } from '@mui/material/styles'
import { CssBaseline, Box, Container, Typography, TextField, Button, IconButton, Avatar, Divider, Grid, Card, CardContent } from '@mui/material'
import { Settings, Send, Mic, MusicNote } from '@mui/icons-material'
import Waveform from './components/Waveform'
import theme from './theme'

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
        body: JSON.stringify({ mood, emoji: selectedEmoji, user_id: user?.id }),
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

  // Parse user from query after backend redirect, or handle code (legacy)
  useEffect(() => {
    const url = new URL(window.location.href)
    const uid = url.searchParams.get('user_id')
    const display = url.searchParams.get('display_name')
    if (uid) {
      setUser({ user_id: Number(uid), display_name: display || '' })
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
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box className="relative flex h-auto min-h-screen w-full flex-col overflow-x-hidden bg-background-light dark:bg-background-dark">
        <Box className="layout-container flex h-full grow flex-col">
          {/* Header */}
          <Box className="flex items-center justify-between whitespace-nowrap border-b border-white/10 px-6 sm:px-10 py-4">
            <Box className="flex items-center gap-3 text-white">
              <svg className="size-6 text-accent-green" fill="none" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                <path clipRule="evenodd" d="M24 0.757355L47.2426 24L24 47.2426L0.757355 24L24 0.757355ZM21 35.7574V12.2426L9.24264 24L21 35.7574Z" fill="currentColor" fillRule="evenodd"></path>
              </svg>
              <Typography variant="h2" className="text-xl font-bold">Melo</Typography>
            </Box>
            <Box className="flex items-center gap-4">
              <IconButton className="group flex items-center justify-center rounded-full size-10 bg-white/10 dark:bg-accent-green/10 hover:bg-white/20 dark:hover:bg-accent-green/20 transition-colors">
                <Settings className="text-white" />
              </IconButton>
              <Avatar 
                className="size-10 rounded-full bg-cover bg-center" 
                src={user?.images?.[0]?.url || "https://lh3.googleusercontent.com/aida-public/AB6AXuA4-Epl-YdKDFbKqtPAsdKWPTt9fsPQCQomkJV5oLnlz5AraVcBFfKaOBC2HvNT2oTF4gfdqKjbY8fvc1HE0IjCgu4frqisqxsS2wSiGI38BxP834rWLyaAL2JDuU5EaQlIHGZ45ZGlj2JFnGRb6SmEdL-s87HizcBsePINWahptNvEk4c0hetAN0Vvcmh3pfOmya77Ain5DbQ6s5pz7vhEjBec0i_evN_ekP4Ynhe2cmzoc1iBq38_hl3ntF_OdQN7Q6BJEf8BXx6z"}
              />
            </Box>
          </Box>

          {/* Main Content */}
          <Box component="main" className="flex flex-1 flex-col items-center px-4 py-8 sm:px-6">
            <Container maxWidth="sm" className="w-full space-y-8">
              <Box className="text-center">
                <Typography variant="h1" className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
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
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      borderColor: 'rgba(53, 158, 255, 0.3)',
                      backgroundColor: 'rgba(245, 247, 248, 0.05)',
                      color: 'white',
                      paddingRight: '60px', // Make space for the button
                      '& fieldset': {
                        borderColor: 'rgba(53, 158, 255, 0.3)',
                      },
                      '&:hover fieldset': {
                        borderColor: '#2EFFC7',
                      },
                      '&.Mui-focused fieldset': {
                        borderColor: '#2EFFC7',
                        boxShadow: '0 0 15px rgba(46,255,199,0.2)',
                      },
                    },
                    '& .MuiInputBase-input': {
                      color: 'white',
                      paddingRight: '60px', // Ensure text doesn't overlap with button
                      '&::placeholder': {
                        color: 'rgba(255, 255, 255, 0.5)',
                        opacity: 1,
                      },
                    },
                  }}
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
                  <Send sx={{ color: 'rgba(255, 255, 255, 0.7)', fontSize: '20px' }} />
                </IconButton>
              </Box>

              {/* Divider */}
              <Box className="flex items-center gap-4">
                <Box className="h-px flex-1 bg-white/10"></Box>
                <Typography className="text-sm font-medium text-white/60">OR</Typography>
                <Box className="h-px flex-1 bg-white/10"></Box>
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
                      onClick={() => setSelectedEmoji(isSelected ? '' : emoji)}
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
                  className="w-full rounded-xl bg-accent-green py-4 text-center font-bold text-background-dark transition-transform hover:scale-105 shadow-[0_0_25px_rgba(46,255,199,0.4)]"
                  sx={{
                    backgroundColor: '#2EFFC7',
                    color: '#0f1923',
                    '&:hover': {
                      backgroundColor: '#26e6b8',
                    },
                  }}
                >
                  Generate Playlist
                </Button>

                <Button
                  fullWidth
                  variant="outlined"
                  onClick={startListening}
                  disabled={listening}
                  className="group flex w-full items-center justify-center gap-2 rounded-xl bg-primary/20 dark:bg-primary/30 py-3 text-center font-semibold text-white transition-colors hover:bg-primary/30 dark:hover:bg-primary/40"
                  sx={{
                    backgroundColor: 'rgba(53, 158, 255, 0.2)',
                    borderColor: 'rgba(53, 158, 255, 0.3)',
                    color: 'white',
                    '&:hover': {
                      backgroundColor: 'rgba(53, 158, 255, 0.3)',
                    },
                  }}
                >
                  <Mic />
                  <span>{listening ? 'Listening...' : 'Record voice'}</span>
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
                >
                  <MusicNote />
                  <span>Connect to Spotify</span>
                </Button>
              </Box>
            </Container>
          </Box>

          {/* Footer with Equalizer */}
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
        </Box>

        {/* Loading Waveform */}
        {loading && (
          <Box className="mt-10">
            <Waveform active={loading} />
          </Box>
        )}

        {/* Playlist Results */}
        {playlist && (
          <Box className="mt-8 px-4">
            <Container maxWidth="lg">
              <Typography variant="h2" className="text-xl font-semibold mb-3 text-white">
                Your Playlist
              </Typography>
              <Typography className="text-sm text-gray-400 mb-4">
                Params: {JSON.stringify(playlist.params)}
              </Typography>
              <Grid container spacing={2}>
                {playlist.tracks.map((t) => (
                  <Grid item xs={12} md={6} key={t.id}>
                    <Card className="p-4 rounded-lg bg-white/5 border border-white/10">
                      <CardContent className="flex items-center gap-4 p-0">
                        {t.image_url && (
                          <img src={t.image_url} alt="album art" className="w-16 h-16 object-cover rounded" />
                        )}
                        <Box className="flex-1">
                          <Typography className="font-medium text-white">{t.name}</Typography>
                          <Typography className="text-sm text-gray-400">{t.artists.join(', ')}</Typography>
                          {t.preview_url ? (
                            <audio controls src={t.preview_url} className="mt-2 w-full" />
                          ) : (
                            <Typography className="text-xs text-gray-500 mt-2">No preview available</Typography>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
              {playlist && (
                <Box className="mt-4 text-center">
                  <Button
                    variant="contained"
                    onClick={savePlaylist}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded"
                    sx={{
                      backgroundColor: '#059669',
                      '&:hover': {
                        backgroundColor: '#047857',
                      },
                    }}
                  >
                    Save Playlist
                  </Button>
                </Box>
              )}
            </Container>
          </Box>
        )}
      </Box>
    </ThemeProvider>
  )
}
