// src/components/common/OtherModulesCards.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Grid,
  Card,
  Chip,
  Button
} from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import SyncAltIcon from '@mui/icons-material/SyncAlt';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { MODULES } from '../../config/modules';

export default function OtherModulesCards({ currentModuleId }) {
  const navigate = useNavigate();

  const otherModules = MODULES.filter((m) => m.id !== currentModuleId && m.enabled);

  if (otherModules.length === 0) return null;

  const getModuleIcon = (id, color) => {
    switch (id) {
      case 'add_vltd':
        return <AddCircleOutlineIcon sx={{ fontSize: 26, color }} />;
      case 'delete_vltd':
        return <LockOpenIcon sx={{ fontSize: 26, color }} />;
      case 'replace_vltd':
        return <SyncAltIcon sx={{ fontSize: 26, color }} />;
      default:
        return <ArrowForwardIcon sx={{ fontSize: 26, color }} />;
    }
  };

  return (
    <Box sx={{ my: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <div>
          <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 1 }}>
            <span>⚡ Other Available Modules</span>
          </Typography>
          <Typography variant="caption" sx={{ color: '#94a3b8' }}>
            Quickly switch between parallel VAHAN workflows while preserving active browser sessions.
          </Typography>
        </div>
      </Box>

      <Grid container spacing={2}>
        {otherModules.map((mod) => (
          <Grid item xs={12} sm={6} md={12 / Math.min(otherModules.length, 3)} key={mod.id}>
            <Card
              onClick={() => navigate(mod.route)}
              sx={{
                p: 2.5,
                height: '100%',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: 'rgba(17, 24, 39, 0.75)',
                backdropFilter: 'blur(16px)',
                borderRadius: '14px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                transition: 'all 0.25s ease-in-out',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  borderColor: mod.color,
                  boxShadow: `0 8px 24px ${mod.color}25`,
                  background: 'rgba(17, 24, 39, 0.9)',
                },
              }}
            >
              <div>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 12,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: `${mod.color}20`,
                      boxShadow: `0 4px 12px ${mod.color}15`,
                    }}
                  >
                    {getModuleIcon(mod.id, mod.color)}
                  </div>
                  <Chip
                    label={mod.badge}
                    size="small"
                    sx={{
                      backgroundColor: `${mod.color}18`,
                      color: mod.color,
                      fontWeight: 700,
                      border: `1px solid ${mod.color}35`,
                      fontSize: '0.72rem',
                    }}
                  />
                </Box>

                <Typography variant="h6" sx={{ fontWeight: 800, color: '#f8fafc', fontSize: '1.05rem', mb: 0.5 }}>
                  {mod.name}
                </Typography>

                <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.85rem', lineHeight: 1.5, mb: 2 }}>
                  {mod.description}
                </Typography>
              </div>

              <Box sx={{ pt: 1, borderTop: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: mod.color, fontWeight: 700, fontFamily: 'monospace' }}>
                  {mod.route}
                </Typography>
                <Button
                  size="small"
                  endIcon={<ArrowForwardIcon fontSize="small" />}
                  sx={{
                    color: mod.color,
                    fontWeight: 700,
                    textTransform: 'none',
                    p: 0,
                    '&:hover': { background: 'transparent' },
                  }}
                >
                  Switch Module
                </Button>
              </Box>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

