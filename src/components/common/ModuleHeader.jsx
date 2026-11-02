// src/components/common/ModuleHeader.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Typography, Chip, Button } from '@mui/material';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import DashboardIcon from '@mui/icons-material/Dashboard';
import { MODULES } from '../../config/modules';

export default function ModuleHeader({ currentModuleId, title, badge, description, color = '#6366f1' }) {
  const navigate = useNavigate();

  const otherModules = MODULES.filter((m) => m.id !== currentModuleId && m.enabled);

  return (
    <div className="glass-panel" style={{ padding: '1.5rem 2rem', marginBottom: '1.5rem', borderLeft: `4px solid ${color}` }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
        <div>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#f8fafc' }}>
              {title}
            </Typography>
            {badge && (
              <Chip
                label={badge}
                size="small"
                sx={{
                  backgroundColor: `${color}25`,
                  color: color,
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  border: `1px solid ${color}40`,
                }}
              />
            )}
          </Box>
          <Typography variant="body2" sx={{ color: '#94a3b8', maxWidth: 720 }}>
            {description}
          </Typography>
        </div>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<DashboardIcon />}
            onClick={() => navigate('/')}
            sx={{ borderColor: 'rgba(255, 255, 255, 0.15)', color: '#cbd5e1', textTransform: 'none' }}
          >
            Dashboard
          </Button>
          {otherModules.map((mod) => (
            <Button
              key={mod.id}
              variant="outlined"
              size="small"
              startIcon={<SwapHorizIcon />}
              onClick={() => navigate(mod.route)}
              sx={{
                borderColor: `${mod.color}50`,
                color: mod.color,
                textTransform: 'none',
                '&:hover': {
                  borderColor: mod.color,
                  backgroundColor: `${mod.color}15`,
                },
              }}
            >
              Switch to {mod.shortTitle}
            </Button>
          ))}
        </Box>
      </Box>
    </div>
  );
}

