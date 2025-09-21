import React, { useEffect, useRef } from 'react'

// Simple animated placeholder waveform (CSS-driven)
export default function Waveform({ active = false }) {
  const bars = Array.from({ length: 24 })
  return (
    <div className="flex items-end gap-1 h-16 overflow-hidden">
      {bars.map((_, i) => (
        <div
          key={i}
          className={`w-1 rounded bg-cyan-400/70 ${active ? 'animate-pulse' : ''}`}
          style={{ height: `${(Math.sin(i) * 0.5 + 0.5) * 64 + 8}px`, animationDelay: `${i * 40}ms` }}
        />
      ))}
    </div>
  )
}

