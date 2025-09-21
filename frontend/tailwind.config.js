/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: "#359EFF",
        "accent-green": "#2EFFC7",
        "background-light": "#f5f7f8",
        "background-dark": "#0f1923",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"]
      },
      borderRadius: {
        DEFAULT: "0.5rem",
        lg: "1rem",
        xl: "1.5rem",
        full: "9999px"
      },
      animation: {
        'pulse-equalizer': 'pulse-equalizer 1.5s infinite ease-in-out',
      },
      keyframes: {
        'pulse-equalizer': {
          '0%, 100%': { transform: 'scaleY(0.2)' },
          '50%': { transform: 'scaleY(1)' },
        }
      }
    },
  },
  plugins: [],
}

