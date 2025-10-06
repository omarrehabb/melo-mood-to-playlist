import React from 'react'
import { Card, CardContent, Box, Typography } from '@mui/material'

export default function SongCard({ track }) {
  const { name, artists = [], image_url, duration_ms } = track || {}

  const formatDuration = (ms) => {
    if (!ms || isNaN(ms)) return ''
    const total = Math.max(0, Math.floor(ms / 1000))
    const m = Math.floor(total / 60)
    const s = total % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <Card
      className="rounded-lg border border-white/10"
      sx={{
        height: 300,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'rgba(255,255,255,0.04)',
        overflow: 'hidden',
        width: '100%',
        minWidth: 190,
        maxWidth: 200,
        mx: 'auto',
      }}
    >
      {/* Fixed-size cover on top to normalize card height */}
      <Box sx={{ position: 'relative', width: '100%', height: 140, overflow: 'hidden' }}>
        {image_url ? (
          <img
            src={image_url}
            alt="album art"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
          />
        ) : (
          <Box sx={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(255,255,255,0.08)' }} />
        )}
      </Box>
      {/* Details */}
      <CardContent sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 0.5, flex: 1, overflow: 'hidden' }}>
        <Typography
          sx={{
            color: 'text.primary',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
            fontWeight: 600,
            fontSize: 15,
            lineHeight: 1.3,
          }}
        >
          {name}
        </Typography>
        <Typography
          sx={{
            color: 'text.secondary',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
            fontSize: 13,
            lineHeight: 1.3,
          }}
        >
          {artists.join(', ')}
        </Typography>
        <Box sx={{ mt: 'auto', display: 'flex', justifyContent: 'flex-end' }}>
          <Typography sx={{ color: 'text.secondary', fontSize: 12 }}>{formatDuration(duration_ms)}</Typography>
        </Box>
      </CardContent>
    </Card>
  )
}
