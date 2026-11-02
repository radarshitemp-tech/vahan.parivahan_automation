// src/components/common/BrowserSessionCard.jsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Button,
  Typography,
  Chip,
  CircularProgress,
  Tooltip,
  Alert
} from '@mui/material';
import OpenInBrowserIcon from '@mui/icons-material/OpenInBrowser';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import CloseIcon from '@mui/icons-material/Close';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { commonApi } from '../../services/commonApi';
import { addApi } from '../../services/addApi';

export default function BrowserSessionCard({ onSessionChange, compact = false }) {
  const [session, setSession] = useState({
    is_alive: false,
    is_authenticated: false,
    current_url: null,
    title: null,
    message: 'Checking session...'
  });
  const [loadingAction, setLoadingAction] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  const fetchSession = useCallback(async () => {
    const s = await commonApi.getSessionStatus();
    setSession(s);
    if (onSessionChange) onSessionChange(s);
  }, [onSessionChange]);

  useEffect(() => {
    fetchSession();
    const timer = setInterval(fetchSession, 8000);
    return () => clearInterval(timer);
  }, [fetchSession]);

  const handleLaunch = async () => {
    setLoadingAction('launch');
    setErrorMsg(null);
    try {
      await addApi.inspectPortal();
      await fetchSession();
    } catch (e) {
      setErrorMsg(e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleConfirmLogin = async () => {
    setLoadingAction('confirm');
    setErrorMsg(null);
    try {
      await addApi.confirmLoginAndInspect();
      await fetchSession();
    } catch (e) {
      setErrorMsg(e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleClose = async () => {
    setLoadingAction('close');
    setErrorMsg(null);
    try {
      await commonApi.closeBrowser();
      await fetchSession();
    } catch (e) {
      setErrorMsg(e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: compact ? '1rem 1.25rem' : '1.5rem', marginBottom: '1.5rem' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, mb: compact ? 1 : 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: session.is_authenticated ? 'rgba(16, 185, 129, 0.15)' : session.is_alive ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              color: session.is_authenticated ? '#10b981' : session.is_alive ? '#f59e0b' : '#ef4444'
            }}
          >
            <OpenInBrowserIcon fontSize="small" />
          </div>
          <div>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 1 }}>
              Shared VAHAN Chrome Session
              <Chip
                size="small"
                label={session.is_authenticated ? 'Authenticated' : session.is_alive ? 'Browser Open (Login Needed)' : 'Disconnected'}
                color={session.is_authenticated ? 'success' : session.is_alive ? 'warning' : 'default'}
                sx={{ fontSize: '0.72rem', height: 22 }}
              />
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>
              {session.current_url ? `Landed on: ${session.current_url}` : session.message || 'Browser is idle'}
            </Typography>
          </div>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {!session.is_alive ? (
            <Button
              variant="contained"
              size="small"
              startIcon={loadingAction === 'launch' ? <CircularProgress size={14} color="inherit" /> : <OpenInBrowserIcon />}
              onClick={handleLaunch}
              disabled={!!loadingAction}
              sx={{ backgroundColor: '#6366f1', '&:hover': { backgroundColor: '#4f46e5' } }}
            >
              Launch Vahan Portal
            </Button>
          ) : (
            <>
              {!session.is_authenticated && (
                <Button
                  variant="contained"
                  size="small"
                  color="warning"
                  startIcon={loadingAction === 'confirm' ? <CircularProgress size={14} color="inherit" /> : <VerifiedUserIcon />}
                  onClick={handleConfirmLogin}
                  disabled={!!loadingAction}
                >
                  Confirm Manual Login
                </Button>
              )}
              <Tooltip title="Refresh session status">
                <Button
                  variant="outlined"
                  size="small"
                  onClick={fetchSession}
                  sx={{ borderColor: 'rgba(255, 255, 255, 0.15)', color: '#94a3b8' }}
                >
                  <RefreshIcon fontSize="small" />
                </Button>
              </Tooltip>
              <Button
                variant="outlined"
                size="small"
                color="error"
                startIcon={<CloseIcon />}
                onClick={handleClose}
                disabled={!!loadingAction}
              >
                Close Browser
              </Button>
            </>
          )}
        </Box>
      </Box>

      {errorMsg && (
        <Alert severity="error" sx={{ mt: 1.5, py: 0.5, backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5' }}>
          {errorMsg}
        </Alert>
      )}

      {session.is_alive && !session.is_authenticated && (
        <Alert
          severity="info"
          icon={<WarningAmberIcon fontSize="inherit" />}
          sx={{ mt: 1.5, py: 0.5, backgroundColor: 'rgba(245, 158, 11, 0.08)', color: '#fcd34d', border: '1px solid rgba(245, 158, 11, 0.2)' }}
        >
          Browser window opened. Please complete your username, password, and CAPTCHA in Chrome, then click "Confirm Manual Login".
        </Alert>
      )}
    </div>
  );
}

