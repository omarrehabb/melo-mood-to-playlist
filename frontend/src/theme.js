import { createTheme } from '@mui/material/styles';

export const makeTheme = (mode = 'dark') =>
  createTheme({
    palette: {
      mode,
      primary: { main: '#359EFF' },
      secondary: { main: '#2EFFC7' },
      background: {
        // Softer, creamish background for light mode to ease contrast
        default: mode === 'dark' ? '#0f1923' : '#F8F6F1',
        paper: mode === 'dark' ? '#0f1923' : '#FFFFFF',
      },
      text: {
        primary: mode === 'dark' ? '#ffffff' : '#0f1923',
        secondary: mode === 'dark' ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.6)',
      },
    },
    typography: {
      fontFamily: '"Sora", "Space Grotesk", "Roboto", "Helvetica", "Arial", sans-serif',
      h1: { fontWeight: 700, fontSize: '2.5rem', lineHeight: 1.2 },
      h2: { fontWeight: 700, fontSize: '1.5rem', lineHeight: 1.3 },
      button: { fontWeight: 600, textTransform: 'none' },
    },
    shape: { borderRadius: 8 },
    components: {
      MuiButton: {
        styleOverrides: {
          root: { borderRadius: 12, textTransform: 'none', fontWeight: 600 },
        },
      },
      MuiTextField: {
        styleOverrides: { root: { '& .MuiOutlinedInput-root': { borderRadius: 12 } } },
      },
    },
  });

// Keep default export for existing imports (dark by default)
const theme = makeTheme('dark');
export default theme;
