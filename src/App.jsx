import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { CsvProvider } from './context/CsvContext';
import { VahanAutomationProvider } from './context/VahanAutomationContext';
import Navbar from './components/Navbar';
import HomePage from './pages/HomePage';
import ExtractPage from './pages/ExtractPage';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#6366f1',
      light: '#818cf8',
      dark: '#4f46e5',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#ec4899',
      light: '#f472b6',
      dark: '#db2777',
    },
    background: {
      default: '#0a0e17',
      paper: '#111827',
    },
    text: {
      primary: '#f8fafc',
      secondary: '#94a3b8',
    },
    success: {
      main: '#10b981',
    },
    error: {
      main: '#ef4444',
    },
  },
  typography: {
    fontFamily: "'Plus Jakarta Sans', 'Outfit', sans-serif",
    h1: { fontFamily: "'Outfit', sans-serif" },
    h2: { fontFamily: "'Outfit', sans-serif" },
    h3: { fontFamily: "'Outfit', sans-serif" },
    h4: { fontFamily: "'Outfit', sans-serif" },
    h5: { fontFamily: "'Outfit', sans-serif" },
    h6: { fontFamily: "'Outfit', sans-serif" },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 4px 14px rgba(99, 102, 241, 0.3)',
          },
        },
      },
    },
  },
});

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <CsvProvider>
        <VahanAutomationProvider>
          <Router>
            <div className="app-layout">
              <Navbar />
              <main className="main-content">
                <Routes>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/extract" element={<ExtractPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </main>
              <footer className="app-footer">
                <p>ONE SOL • High-Performance CSV Ingestion & Extraction Platform</p>
              </footer>
            </div>
          </Router>
        </VahanAutomationProvider>
      </CsvProvider>
    </ThemeProvider>
  );
}
