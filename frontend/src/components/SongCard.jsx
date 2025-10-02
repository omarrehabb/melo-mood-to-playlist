import React from 'react'
import { Card, CardContent, Box, Typography } from '@mui/material'

export default function SongCard({ track }) {
  const { name, artists = [], image_url, preview_url, duration_ms } = track || {}

  const formatDuration = (ms) => {
    if (!ms || isNaN(ms)) return ''
    const total = Math.max(0, Math.floor(ms / 1000))
    const m = Math.floor(total / 60)
    const s = total % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }
  return (
    <Card className="rounded-lg bg-white/5 border border-white/10" sx={{ height: 180 }}>
      <CardContent className="flex gap-3 p-3 h-full items-start">
        <Box className="w-12 shrink-0">
          {image_url ? (
            <img
              src={image_url}
              alt="album art"
              className="w-12 h-12 object-cover rounded"
            />
          ) : (
            <Box className="w-12 h-12 rounded bg-white/10" />
          )}
        </Box>
        <Box className="flex-1 flex flex-col min-w-0 h-full">
          <Typography className="font-medium text-white" sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {name}
          </Typography>
          <Box className="flex items-center justify-between gap-2">
            <Typography className="text-sm text-gray-400" sx={{ display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {artists.join(', ')}
            </Typography>
            <Typography className="text-xs text-gray-400 shrink-0">
              {formatDuration(duration_ms)}
            </Typography>
          </Box>
          <Box className="mt-auto w-full" sx={{ height: 32 }}>
            {preview_url ? (
              <audio controls src={preview_url} className="w-full h-full" />
            ) : null}
          </Box>
        </Box>
      </CardContent>
    </Card>
  )
}
