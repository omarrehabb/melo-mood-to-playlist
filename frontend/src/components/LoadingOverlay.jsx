import React from 'react'

export default function LoadingOverlay({ text = 'Generating your playlist…' }) {
  const bars = Array.from({ length: 10 })
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4">
        <div className="flex items-end gap-1 h-10">
          {bars.map((_, i) => (
            <div
              key={i}
              className="w-2 rounded bg-accent-green"
              style={{
                height: '8px',
                animation: 'melo-bounce 900ms ease-in-out infinite',
                animationDelay: `${i * 60}ms`,
              }}
            />
          ))}
        </div>
        <div className="text-white/80 text-sm font-medium">{text}</div>
      </div>

      <style>{`
        @keyframes melo-bounce {
          0%, 100% { transform: scaleY(0.6); opacity: 0.7; }
          50% { transform: scaleY(1.6); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

