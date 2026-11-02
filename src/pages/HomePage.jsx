// src/pages/HomePage.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCsv } from '../context/CsvContext';
import {
  Button,
  Typography,
  Box,
  Alert,
  Grid,
  Chip,
  Card
} from '@mui/material';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import SyncAltIcon from '@mui/icons-material/SyncAlt';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import BrowserSessionCard from '../components/common/BrowserSessionCard';
import { MODULES } from '../config/modules';

export default function HomePage() {
  const navigate = useNavigate();
  const { csvData, fileName, metadata, error } = useCsv();

  return (
    <div className="fade-in">
      {/* Hero Section */}
      <section className="hero-wrapper" style={{ marginBottom: '2rem' }}>
        <div className="hero-pill">
          <span>⚡ VAHAN VLTD Automation Studio & Multi-Module Engine</span>
        </div>
        <h1 className="hero-title">
          <span className="hero-gradient-text">Automation & Data Hub</span>
        </h1>
        <p className="hero-subtitle">
          Modular automation platform for Parivahan VAHAN portal operations. Select an automation module to begin.
        </p>

        {error && (
          <Box sx={{ maxWidth: 650, mx: 'auto', mb: 3 }}>
            <Alert severity="error" sx={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5' }}>
              {error}
            </Alert>
          </Box>
        )}
      </section>

      {/* Shared Chrome Browser Session Banner */}
      <BrowserSessionCard compact />

      {/* Active Dataset Banner */}
      {csvData.length > 0 && metadata && (
        <div className="glass-panel" style={{ padding: '1.25rem 2rem', marginBottom: '2rem', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <CheckCircleIcon sx={{ color: '#10b981', fontSize: 30 }} />
              <div>
                <Typography variant="subtitle1" sx={{ color: '#fff', fontWeight: 700 }}>
                  Active CSV Dataset: {fileName}
                </Typography>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Parsed {metadata.rowCount} rows & {metadata.columnCount} columns
                </Typography>
              </div>
            </Box>
            <Box sx={{ display: 'flex', gap: 1.5 }}>
              <Button
                variant="contained"
                size="small"
                onClick={() => navigate('/modules/add')}
                sx={{ backgroundColor: '#10b981', '&:hover': { backgroundColor: '#059669' } }}
              >
                Inspect in Add Module
              </Button>
            </Box>
          </Box>
        </div>
      )}

      {/* Central Module Selection Dashboard: Pure Card Views */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ fontWeight: 800, color: '#f8fafc', mb: 2.5 }}>
          Available Automation Modules
        </Typography>

        <Grid container spacing={3}>
          {MODULES.map((module) => (
            <Grid item xs={12} sm={6} md={4} key={module.id}>
              <Card
                onClick={() => navigate(module.route)}
                sx={{
                  height: '100%',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  background: 'rgba(17, 24, 39, 0.75)',
                  backdropFilter: 'blur(20px)',
                  borderRadius: '16px',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  p: 3,
                  transition: 'all 0.25s ease-in-out',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    borderColor: module.color,
                    boxShadow: `0 12px 30px ${module.color}25`,
                    background: 'rgba(17, 24, 39, 0.9)',
                  },
                }}
              >
                <div>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2.5 }}>
                    <div
                      style={{
                        width: 52,
                        height: 52,
                        borderRadius: 14,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: `${module.color}20`,
                        color: module.color,
                        boxShadow: `0 4px 12px ${module.color}15`,
                      }}
                    >
                      {module.id === 'add_vltd' ? (
                        <AddCircleOutlineIcon sx={{ fontSize: 28 }} />
                      ) : module.id === 'replace_vltd' ? (
                        <SyncAltIcon sx={{ fontSize: 28 }} />
                      ) : (
                        <LockOpenIcon sx={{ fontSize: 28 }} />
                      )}
                    </div>
                    <Chip
                      label={module.badge}
                      size="small"
                      sx={{
                        backgroundColor: `${module.color}15`,
                        color: module.color,
                        fontWeight: 700,
                        border: `1px solid ${module.color}35`,
                        fontSize: '0.75rem',
                      }}
                    />
                  </Box>

                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#f8fafc', mb: 1 }}>
                    {module.name}
                  </Typography>

                  <Typography variant="body2" sx={{ color: '#94a3b8', lineHeight: 1.6, mb: 3 }}>
                    {module.description}
                  </Typography>
                </div>

                <Button
                  variant="contained"
                  fullWidth
                  endIcon={<ArrowForwardIcon />}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(module.route);
                  }}
                  sx={{
                    background: module.gradient,
                    color: '#fff',
                    fontWeight: 700,
                    py: 1.2,
                    borderRadius: '10px',
                    textTransform: 'none',
                    fontSize: '0.92rem',
                    boxShadow: 'none',
                    '&:hover': {
                      boxShadow: `0 6px 18px ${module.color}40`,
                    },
                  }}
                >
                  Launch {module.shortTitle}
                </Button>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    </div>
  );
}
